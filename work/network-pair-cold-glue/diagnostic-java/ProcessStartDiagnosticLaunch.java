package net.neoforged.fml.loading.diagnostic;

import java.io.PrintStream;
import java.util.List;

/** Diagnostic derivative only. Call after preLaunch returns, before Minecraft Main. */
public final class ProcessStartDiagnosticLaunch {
    private static boolean attempted;
    private static ProcessStartDiagnostic capture;
    private static Thread drain;
    private static volatile boolean outputFailed;
    private ProcessStartDiagnosticLaunch() { }

    /** Fixed-message, cause-free, stack-free refusal. No fallback to ordinary launch. */
    public static final class Refused extends RuntimeException {
        private static final long serialVersionUID = 1L;
        private Refused() { super("diagnostic launch refused", null, false, false); }
    }

    public static void startOrThrow() {
        start(System.out, ProcessStartDiagnostic.Limits.maximum());
    }

    static synchronized void start(PrintStream sink, ProcessStartDiagnostic.Limits limits) {
        if (attempted) throw new Refused();
        attempted = true; // Never renew the capture or drain window, including after failure.
        try {
            if (sink == null) throw new Refused();
            capture = ProcessStartDiagnostic.open(true, limits);
            if (capture.snapshot().reason() != ProcessStartDiagnostic.Reason.ACTIVE)
                throw new Refused();
            drain = new Thread(() -> pump(sink), "processbuilder-diagnostic-output");
            drain.setDaemon(true);
            drain.start();
        } catch (Throwable ignored) {
            if (capture != null) capture.stop();
            throw new Refused();
        }
    }

    private static void pump(PrintStream sink) {
        int sent = 0;
        try {
            emit(sink, "{\"kind\":\"processbuilder_diagnostic_status\",\"state\":\"STARTED\",\"diagnostic_only\":true,\"admission_evidence\":false}");
            while (true) {
                // Read stop state FIRST, then the immutable event snapshot. If stopped,
                // all admitted events are now included; late decoding is inert.
                boolean stopped = capture.snapshot().stopped();
                List<ProcessStartDiagnostic.Event> events = capture.events();
                while (sent < events.size()) emit(sink, events.get(sent++).json());
                if (stopped) {
                    emit(sink, "{\"kind\":\"processbuilder_diagnostic_status\",\"state\":\""
                            + capture.snapshot().reason().name()
                            + "\",\"diagnostic_only\":true,\"admission_evidence\":false}");
                    return;
                }
                Thread.sleep(10);
            }
        } catch (Throwable ignored) {
            outputFailed = true;
            capture.stop(); // Never inspect/render the exception or retry the sink.
        }
    }

    private static void emit(PrintStream sink, String safeAscii) {
        sink.println(safeAscii);
        if (sink.checkError()) throw new Refused();
    }

    static synchronized ProcessStartDiagnostic captureForTest() { return capture; }
    static synchronized Thread drainForTest() { return drain; }
    static boolean outputFailedForTest() { return outputFailed; }
}
