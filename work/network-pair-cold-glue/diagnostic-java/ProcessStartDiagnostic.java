package net.neoforged.fml.loading.diagnostic;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Filter;
import java.util.logging.Level;
import java.util.logging.LogManager;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

/**
 * Source-only diagnostic for the pinned JDK and a trusted, frozen JUL profile.
 * Not an executable-identity, process-admission, security, or provenance boundary.
 * The installed rejecting filter and its strong owner persist until JVM death.
 * Never changes handlers, parent routing, global configuration, or system properties.
 */
public final class ProcessStartDiagnostic {
    public static final String LOGGER_NAME = "java.lang.ProcessBuilder";
    private static final Object OWNER_LOCK = new Object();
    private static ProcessStartDiagnostic owner;
    private static final String PREFIX = "ProcessBuilder.start(): pid: ";
    private static final String COMMAND_MARKER = ", cmd: \"";
    private static final int MAX_MESSAGE_CHARS = 4096;
    private static final int MAX_DIRECTORY_CHARS = 2048;
    private static final int MAX_STACK_FRAMES = 64;

    public enum Reason {
        ACTIVE, DISABLED, STOPPED, EXPIRED, RECORD_LIMIT, EVENT_LIMIT, OUTPUT_LIMIT,
        UNSUPPORTED_MANAGER, UNSUPPORTED_PROVIDER, UNSUPPORTED_LOGGER,
        UNSUPPORTED_FILTER, DEBUG_ALREADY_ENABLED, SECURITY_RESTRICTION,
        ALREADY_OWNED, SETUP_FAILED, CAPTURE_FAILED
    }

    // Deterministic faults are package-private and used only by isolated test JVMs.
    enum SetupFault { NONE, AFTER_FILTER, AFTER_OFF, BEFORE_WATCHDOG,
        AFTER_WATCHDOG, AFTER_DEBUG }
    enum DecodeFault { NONE, RUNTIME, ERROR }
    private static final RuntimeException INJECTED_RUNTIME = new RuntimeException();
    private static final Error INJECTED_ERROR = new Error();

    public record Limits(Duration lifetime, int records, int events, int outputBytes) {
        public Limits {
            if (lifetime == null || lifetime.compareTo(Duration.ofMillis(25)) < 0
                    || lifetime.compareTo(Duration.ofSeconds(30)) > 0
                    || records < 1 || records > 256 || events < 1 || events > 64
                    || outputBytes < 1 || outputBytes > 16384) {
                throw new IllegalArgumentException("invalid bounded diagnostic limits");
            }
        }
        public static Limits maximum() {
            return new Limits(Duration.ofSeconds(30), 256, 64, 16384);
        }
    }

    public enum RequestedCommand { LSHW, LSPCI, LSCPU, DMIDECODE, SLEEP_FIXTURE }
    public enum Caller { OSHI_EXECUTING_COMMAND_RUN_NATIVE, FIXTURE, OTHER }

    /** Only bounded PID and code-owned enum labels can reach serialization. */
    public record Event(long pid, RequestedCommand requestedCommand, Caller caller) {
        public Event {
            if (pid < 1 || pid > Integer.MAX_VALUE || requestedCommand == null || caller == null)
                throw new IllegalArgumentException("invalid diagnostic event");
        }
        public String json() {
            return "{\"kind\":\"processbuilder_debug\",\"requested_command\":\""
                    + requestedCommand.name() + "\",\"caller\":\"" + caller.name()
                    + "\",\"pid\":" + pid
                    + ",\"diagnostic_only\":true,\"admission_evidence\":false}";
        }
        public boolean admissionEvidence() { return false; }
    }

    public record Snapshot(Reason reason, boolean filterInstalled, boolean stopped,
                           boolean levelOff, int records, int rejected,
                           int events, int outputBytes) { }

    private final Limits limits;
    private final Filter filter = this::suppress;
    private final List<Event> events = new ArrayList<>();
    private final DecodeFault decodeFault;
    private Logger target;
    private long deadline;
    private Reason reason;
    private boolean filterInstalled;
    private boolean levelOff;
    private int records;
    private int rejected;
    private int outputBytes;

    private ProcessStartDiagnostic(Limits limits, Reason reason, DecodeFault fault) {
        this.limits = limits;
        this.reason = reason;
        this.decodeFault = fault;
    }

    public static ProcessStartDiagnostic open(boolean enabled, Limits limits) {
        return openForTest(enabled, limits, SetupFault.NONE, DecodeFault.NONE);
    }

    @SuppressWarnings("removal")
    static ProcessStartDiagnostic openForTest(boolean enabled, Limits limits,
                                                         SetupFault fault, DecodeFault decodeFault) {
        if (limits == null || fault == null || decodeFault == null)
            throw new IllegalArgumentException("diagnostic configuration required");
        var result = new ProcessStartDiagnostic(limits,
                enabled ? Reason.ACTIVE : Reason.DISABLED, decodeFault);
        if (!enabled) return result; // No logger or provider resolution when disabled.
        if (System.getSecurityManager() != null)
            return inactive(limits, Reason.SECURITY_RESTRICTION);
        synchronized (OWNER_LOCK) {
            if (owner != null) return inactive(limits, Reason.ALREADY_OWNED);
            try {
                LogManager manager = LogManager.getLogManager();
                if (manager.getClass() != LogManager.class)
                    return inactive(limits, Reason.UNSUPPORTED_MANAGER);
                System.LoggerFinder finder = System.LoggerFinder.getLoggerFinder();
                Class<?> expected = Class.forName("sun.util.logging.internal.LoggingProviderImpl",
                        false, LogManager.class.getClassLoader());
                if (finder.getClass() != expected
                        || finder.getClass().getModule() != LogManager.class.getModule())
                    return inactive(limits, Reason.UNSUPPORTED_PROVIDER);
                // Resolve BOTH peers before mutation: pinned Logger.ConfigurationData
                // shares level/filter after the system/application logger merge.
                Logger logger = Logger.getLogger(LOGGER_NAME);
                if (logger.getClass() != Logger.class)
                    return inactive(limits, Reason.UNSUPPORTED_LOGGER);
                System.Logger systemLogger = finder.getLogger(LOGGER_NAME, ProcessBuilder.class.getModule());
                if (logger.getFilter() != null)
                    return inactive(limits, Reason.UNSUPPORTED_FILTER);
                if (logger.isLoggable(Level.FINE) || logger.isLoggable(Level.FINER)
                        || systemLogger.isLoggable(System.Logger.Level.DEBUG)
                        || systemLogger.isLoggable(System.Logger.Level.TRACE))
                    return inactive(limits, Reason.DEBUG_ALREADY_ENABLED);

                synchronized (result) {
                    result.target = logger;
                    result.deadline = System.nanoTime() + limits.lifetime().toNanos();
                    owner = result; // One-shot strong owner; NEVER cleared, even on failure.
                    logger.setFilter(result.filter); // Initially DEBUG is still disabled.
                    result.filterInstalled = true;
                    failAt(fault, SetupFault.AFTER_FILTER);
                    logger.setLevel(Level.OFF);
                    failAt(fault, SetupFault.AFTER_OFF);
                    Thread watchdog = new Thread(result::watch, "permanent-processbuilder-diagnostic");
                    watchdog.setDaemon(true);
                    failAt(fault, SetupFault.BEFORE_WATCHDOG);
                    watchdog.start();
                    failAt(fault, SetupFault.AFTER_WATCHDOG);
                    logger.setLevel(Level.FINE); // DEBUG enabled, never TRACE.
                    failAt(fault, SetupFault.AFTER_DEBUG);
                    if (!systemLogger.isLoggable(System.Logger.Level.DEBUG)
                            || systemLogger.isLoggable(System.Logger.Level.TRACE))
                        throw INJECTED_RUNTIME;
                }
            } catch (Throwable ignored) {
                // Fixed reason only: no exception inspection, rendering, or rethrow.
                result.stopCapture(Reason.SETUP_FAILED);
            }
            return result;
        }
    }

    private static ProcessStartDiagnostic inactive(Limits limits, Reason reason) {
        return new ProcessStartDiagnostic(limits, reason, DecodeFault.NONE);
    }

    private static void failAt(SetupFault actual, SetupFault expected) {
        if (actual == expected) throw INJECTED_RUNTIME;
    }

    private boolean suppress(LogRecord record) {
        try {
            accept(record);
        } catch (Throwable ignored) {
            // Never propagate into ProcessBuilder.start() after its child has started.
            // Even VM/resource failures must not intentionally route a raw record onward.
            try { stopCapture(Reason.CAPTURE_FAILED); } catch (Throwable alsoIgnored) { }
        }
        return false; // Every branch, rejection, cap, expiry, stop and caught failure.
    }

    private void accept(LogRecord record) {
        synchronized (this) {
            if (reason != Reason.ACTIVE) return;
            if (System.nanoTime() - deadline >= 0) { stopCapture(Reason.EXPIRED); return; }
            if (records >= limits.records()) { stopCapture(Reason.RECORD_LIMIT); return; }
            records++;
        }
        // A plain RuntimeException still has a foreign, lockable monitor. Do NOT
        // hold the lifecycle lock while calling getStackTrace(). Late results are inert.
        if (decodeFault == DecodeFault.RUNTIME) throw INJECTED_RUNTIME;
        if (decodeFault == DecodeFault.ERROR) throw INJECTED_ERROR;
        Event event = decode(record);
        synchronized (this) {
            if (reason != Reason.ACTIVE) return;
            if (System.nanoTime() - deadline >= 0) { stopCapture(Reason.EXPIRED); return; }
            if (event == null) rejected++;
            else {
                int cost = event.json().length() + 1; // Generated ASCII == UTF-8 byte count.
                if (cost > limits.outputBytes() - outputBytes) {
                    stopCapture(Reason.OUTPUT_LIMIT);
                    return;
                }
                events.add(event);
                outputBytes += cost;
                if (events.size() >= limits.events()) { stopCapture(Reason.EVENT_LIMIT); return; }
            }
            if (records >= limits.records()) stopCapture(Reason.RECORD_LIMIT);
        }
    }

    private static Event decode(LogRecord record) {
        if (record == null || record.getClass() != LogRecord.class) return null;
        if (!LOGGER_NAME.equals(record.getLoggerName()) || record.getLevel() != Level.FINE
                || record.getParameters() != null || record.getResourceBundle() != null
                || record.getResourceBundleName() != null) return null;
        String message = record.getMessage();
        if (message == null || message.length() > MAX_MESSAGE_CHARS || !message.startsWith(PREFIX))
            return null;
        int cursor = PREFIX.length();
        long pid = 0;
        int digits = 0;
        while (cursor < message.length()) {
            char c = message.charAt(cursor);
            if (c < '0' || c > '9') break;
            if (++digits > 10) return null;
            pid = pid * 10 + c - '0';
            if (pid > Integer.MAX_VALUE) return null;
            cursor++;
        }
        if (digits == 0 || pid == 0 || !message.startsWith(", dir: ", cursor)) return null;
        int directoryStart = cursor + ", dir: ".length();
        int commandStart = message.lastIndexOf(COMMAND_MARKER);
        if (commandStart < directoryStart || commandStart - directoryStart > MAX_DIRECTORY_CHARS
                || !message.endsWith("\"")) return null;
        String command = message.substring(commandStart + COMMAND_MARKER.length(), message.length() - 1);
        RequestedCommand requested = switch (command) {
            case "lshw", "/usr/bin/lshw", "/usr/sbin/lshw" -> RequestedCommand.LSHW;
            case "lspci", "/usr/bin/lspci", "/usr/sbin/lspci" -> RequestedCommand.LSPCI;
            case "lscpu", "/usr/bin/lscpu", "/usr/sbin/lscpu" -> RequestedCommand.LSCPU;
            case "dmidecode", "/usr/bin/dmidecode", "/usr/sbin/dmidecode" -> RequestedCommand.DMIDECODE;
            case "/usr/bin/sleep" -> RequestedCommand.SLEEP_FIXTURE;
            default -> null;
        };
        if (requested == null) return null;
        Throwable thrown = record.getThrown();
        if (thrown == null || thrown.getClass() != RuntimeException.class
                || !"ProcessBuilder.start() debug".equals(thrown.getMessage())) return null;
        StackTraceElement[] frames = thrown.getStackTrace();
        if (frames.length < 2 || frames.length > MAX_STACK_FRAMES) return null;
        boolean hasCaller = false;
        Caller caller = Caller.OTHER;
        for (int i = 0; i < frames.length; i++) {
            StackTraceElement frame = frames[i];
            if (frame == null || !safeIdentifier(frame.getClassName(), 256, true)
                    || !safeIdentifier(frame.getMethodName(), 128, false)) return null;
            boolean processStart = "java.lang.ProcessBuilder".equals(frame.getClassName())
                    && "start".equals(frame.getMethodName());
            if (i == 0 && !processStart) return null;
            if (!processStart) {
                hasCaller = true;
                if ("oshi.util.ExecutingCommand".equals(frame.getClassName())
                        && "runNative".equals(frame.getMethodName()))
                    caller = Caller.OSHI_EXECUTING_COMMAND_RUN_NATIVE;
                else if (caller == Caller.OTHER
                        && "net.neoforged.fml.loading.diagnostic.ProcessStartDiagnosticTest".equals(frame.getClassName())
                        && "launchSleep".equals(frame.getMethodName())) caller = Caller.FIXTURE;
            }
        }
        return hasCaller ? new Event(pid, requested, caller) : null;
    }

    private static boolean safeIdentifier(String text, int max, boolean className) {
        if (text == null || text.isEmpty() || text.length() > max) return false;
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            if (!(c >= 'a' && c <= 'z') && !(c >= 'A' && c <= 'Z')
                    && !(c >= '0' && c <= '9') && c != '_' && c != '$'
                    && !(className && c == '.') && !(!className && (c == '<' || c == '>')))
                return false;
        }
        return true;
    }

    private synchronized void stopCapture(Reason stop) {
        if (reason != Reason.ACTIVE) return;
        reason = stop;
        // Permanent filter remains even if setting OFF fails. No restoration path.
        try {
            if (target != null) { target.setLevel(Level.OFF); levelOff = true; }
        } catch (Throwable ignored) { }
        notifyAll();
    }

    private void watch() {
        try {
            synchronized (this) {
                while (reason == Reason.ACTIVE) {
                    long remaining = deadline - System.nanoTime();
                    if (remaining <= 0) { stopCapture(Reason.EXPIRED); return; }
                    wait(Math.max(1, Math.min(100, remaining / 1_000_000)));
                }
            }
        } catch (Throwable ignored) {
            stopCapture(Reason.CAPTURE_FAILED);
        }
    }

    /** Ends capture only. Does NOT uninstall, restore, reset, or release ownership. */
    public void stop() { stopCapture(Reason.STOPPED); }

    public synchronized List<Event> events() { return List.copyOf(events); }
    public synchronized String output() {
        StringBuilder result = new StringBuilder(outputBytes);
        for (Event event : events) result.append(event.json()).append('\n');
        return result.toString();
    }
    public synchronized Snapshot snapshot() {
        return new Snapshot(reason, filterInstalled, reason != Reason.ACTIVE, levelOff,
                records, rejected, events.size(), outputBytes);
    }
    public synchronized boolean awaitStopped(Duration timeout) throws InterruptedException {
        if (timeout == null || timeout.isNegative() || timeout.compareTo(Duration.ofSeconds(31)) > 0)
            throw new IllegalArgumentException("invalid bounded wait");
        long until = System.nanoTime() + timeout.toNanos();
        while (reason == Reason.ACTIVE) {
            long remaining = until - System.nanoTime();
            if (remaining <= 0) return false;
            wait(Math.max(1, remaining / 1_000_000));
        }
        return true;
    }
}
