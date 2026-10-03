package org.sinytra.connector.infinity.inventory;

import com.google.gson.Gson;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.*;
import java.util.*;

/** Internal BOOT entry point. Installation pins come from the source-built host, never mod metadata. */
public final class BootstrapInstallation {
    private static final String RESOURCE = "/META-INF/unified-admission/installation.json";
    public record Artifact(String path, String sha256, List<String> primaryIds, String role) {}
    public record Embedded(String root, List<String> entries, String sha256, List<String> primaryIds,
                           String role, String apiFamily) {}
    public record InputFile(String path, String sha256) {}
    private record Consumer(int protocol, List<String> consumers, String runtimeModelOwner) {}
    public record Policy(int schema, boolean approved, String gameDirectory, String installationDirectory,
                         String launchTarget, String processArgumentsSha256, Map<String, String> properties,
                         Map<String, String> environment, List<Artifact> artifacts, List<Embedded> embedded,
                         List<InputFile> argumentFiles, String policyId) {}
    private BootstrapInstallation() {}

    public static synchronized AdmissionSession open(Path gameDirectory, String launchTarget) {
        try {
            if (AdmissionSession.isInstalled()) {
                AdmissionSession.current().requireLaunch(gameDirectory, launchTarget);
                return AdmissionSession.current();
            }
            if (!"fml_loader".equals(BootstrapInstallation.class.getModule().getName()))
                throw new IOException("Admission must be owned by the source-built fml_loader BOOT module");
            if (AdmissionSession.class.getModule() != BootstrapInstallation.class.getModule()
                || InfrastructurePolicy.class.getModule() != BootstrapInstallation.class.getModule()
                || TrustedPayloads.class.getClassLoader() != BootstrapInstallation.class.getClassLoader())
                throw new IOException("Split admission class ownership");
            Policy policy;
            try (InputStream in = BootstrapInstallation.class.getResourceAsStream(RESOURCE)) {
                if (in == null) throw new IOException("Missing reviewed installation policy; successor is not installable");
                byte[] bytes = in.readNBytes(1024 * 1024 + 1);
                if (bytes.length > 1024 * 1024) throw new IOException("Oversized installation policy");
                policy = new Gson().fromJson(new String(bytes, StandardCharsets.UTF_8), Policy.class);
            }
            validate(policy, gameDirectory, launchTarget);
            return AdmissionSession.initialize(policy);
        } catch (IOException | RuntimeException failure) {
            throw new IllegalStateException("Unified pre-service admission could not establish a complete installation", failure);
        }
    }

    private static void validate(Policy p, Path game, String target) throws IOException {
        if (p == null || p.schema() != 1 || !p.approved() || p.policyId() == null || p.policyId().isBlank())
            throw new IOException("Installation policy is unapproved or has an unsupported schema");
        if (!game.toRealPath().equals(Path.of(p.gameDirectory()).toRealPath()) || !Objects.equals(target, p.launchTarget()))
            throw new IOException("Installation game root or target changed");
        // The first source candidate supports an explicit sealed folder profile. Unsupported inputs fail before SERVICE.
        if (target == null) throw new IOException("Missing launch target");
        for (String key : List.of("fml.modFolders", "fml.modFoldersFile", "mergeModules"))
            if (!System.getProperty(key, "").isBlank()) throw new IOException("Unsupported grouped launch input " + key);
        if (!System.getenv().getOrDefault("MOD_CLASSES", "").isBlank()) throw new IOException("Unsupported MOD_CLASSES input");
        List<String> actualArgs = actualProcessArguments();
        if (!digestStrings(actualArgs).equals(p.processArgumentsSha256())) throw new IOException("Sealed process arguments changed");
        for (String arg : actualArgs) {
            if (arg.startsWith("-javaagent") || arg.startsWith("-agentlib") || arg.startsWith("-agentpath") || arg.startsWith("--patch-module"))
                throw new IOException("Unsupported pre-BOOT code injection option");
            if (arg.equals("--fml.mods") || arg.startsWith("--fml.mods=") || arg.equals("--fml.modLists") || arg.startsWith("--fml.modLists="))
                throw new IOException("Explicit additive mod inputs are unsupported in this sealed folder profile");
        }
        for (String key : List.of("java.class.path", "jdk.module.path", "legacyClassPath", "legacyClassPath.file", "fml.modFolders", "fml.modFoldersFile")) {
            if (!p.properties().containsKey(key) || !Objects.equals(System.getProperty(key, ""), p.properties().get(key)))
                throw new IOException("Unsealed launch property " + key);
        }
        for (String key : List.of("MOD_CLASSES", "JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS")) {
            if (!p.environment().containsKey(key) || !Objects.equals(System.getenv().getOrDefault(key, ""), p.environment().get(key)))
                throw new IOException("Unsealed launch environment " + key);
        }
        for (String key : List.of("JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS"))
            if (!System.getenv().getOrDefault(key, "").isBlank()) throw new IOException("Opaque environment JVM options are unsupported in this sealed profile");
        Path installation = Path.of(p.installationDirectory()).toRealPath();
        Set<Path> pinned = new HashSet<>();
        int owners = 0, consumers = 0, gameComponents = 0, productComponents = 0;
        for (Artifact a : Objects.requireNonNull(p.artifacts())) {
            Path path = authorizedPath(installation, a.path());
            if (!pinned.add(path)) throw new IOException("Duplicate installation artifact origin");
            if (a.role().equals("BOOT_OWNER")) {
                owners++;
                Path owner = ArchiveOrigins.ofClass(BootstrapInstallation.class);
                if (!path.equals(owner) || !"SELF".equals(a.sha256())) throw new IOException("Wrong source-owned BOOT artifact after backing-file verification");
            } else verify(path, a.sha256());
            if (a.role().equals("ADMISSION_CONSUMER")) { verifyConsumer(path); consumers++; }
            if (a.role().equals("COMPATIBILITY_GAME")) { verifyGameComponent(path, "org/sinytra/connector/mod/FmlGameCompatibilityComponent.class"); gameComponents++; }
            if (a.role().equals("PRODUCT_GAME")) { verifyGameComponent(path, "dev/modcompat/runtime/bundle/RuntimeBundle.class"); productComponents++; }
            if (Set.of("ADMISSION_CONSUMER", "COMPATIBILITY_GAME", "PRODUCT_GAME").contains(a.role()) && path.startsWith(game.toRealPath().resolve("mods")))
                throw new IOException("Internal loader components must be installed outside the user mods directory");
            if (!Set.of("PLATFORM", "MANAGED_ROOT", "BOOT_OWNER", "ADMISSION_CONSUMER", "COMPATIBILITY_GAME", "PRODUCT_GAME").contains(a.role())) throw new IOException("Unknown installation artifact role");
            Objects.requireNonNull(a.primaryIds());
        }
        if (owners != 1 || consumers != 1 || gameComponents != 1 || productComponents != 1) throw new IOException("Exactly one BOOT, SERVICE compatibility, GAME compatibility and GAME product owner are required");
        for (String property : List.of("java.class.path", "jdk.module.path", "legacyClassPath")) {
            String value = p.properties().get(property);
            if (value.isEmpty()) continue;
            for (String entry : value.split(java.util.regex.Pattern.quote(File.pathSeparator), -1)) {
                if (entry.isBlank() || entry.contains("*")) throw new IOException("Unsealed wildcard/empty launch path");
                Path path = Path.of(entry).toRealPath();
                if (!Files.isRegularFile(path) || !pinned.contains(path)) throw new IOException("Unpinned launch path " + path);
                for (Artifact artifact : p.artifacts())
                    if (Set.of("ADMISSION_CONSUMER", "COMPATIBILITY_GAME", "PRODUCT_GAME").contains(artifact.role()) && authorizedPath(installation, artifact.path()).equals(path))
                        throw new IOException("Internal layer components cannot also be placed on a raw JVM/legacy classpath");
            }
        }
        var rawRoots = new ArrayList<Path>();
        for (String property : List.of("java.class.path", "jdk.module.path", "legacyClassPath")) {
            String value=p.properties().get(property);
            if (!value.isEmpty()) for (String input : value.split(java.util.regex.Pattern.quote(File.pathSeparator))) rawRoots.add(Path.of(input).toRealPath());
        }
        ArchiveOrigins.requireUniqueModule("fml_loader", ArchiveOrigins.ofClass(BootstrapInstallation.class), rawRoots);
        Set<Path> argumentFiles = new HashSet<>();
        for (InputFile file : Objects.requireNonNull(p.argumentFiles())) {
            Path path = Path.of(file.path()).toRealPath(); verify(path, file.sha256()); argumentFiles.add(path);
            if (Files.size(path) > 1024 * 1024) throw new IOException("Oversized Java argument file");
            String contents = Files.readString(path);
            for (String unsupported : List.of("--fml.mods", "--fml.modLists", "-javaagent", "-agentlib", "-agentpath", "--patch-module"))
                if (contents.contains(unsupported)) throw new IOException("Unsupported code/discovery input in argument file");
        }
        String legacyFile = p.properties().get("legacyClassPath.file");
        if (!legacyFile.isEmpty() && !argumentFiles.contains(Path.of(legacyFile).toRealPath()))
            throw new IOException("Unpinned legacy classpath descriptor file");
        for (String arg : actualArgs) if (arg.startsWith("@") && !arg.startsWith("@@")) {
            Path path = Path.of(arg.substring(1)).toRealPath();
            if (!argumentFiles.contains(path)) throw new IOException("Unpinned Java argument file");
        }
        Objects.requireNonNull(p.embedded());
    }

    private static final int MAX_PROCESS_ARGUMENT_BYTES = 1024 * 1024;
    static List<String> actualProcessArguments() throws IOException {
        Optional<String[]> info = ProcessHandle.current().info().arguments();
        List<String> args;
        String source;
        if (info.isPresent()) { args = List.copyOf(Arrays.asList(info.get())); source = "process_handle"; }
        else {
            if (!"Linux".equals(System.getProperty("os.name"))) throw new IOException("Process argument observation is unavailable on this platform");
            args = readLinuxCommandLine(Path.of("/proc/self/cmdline"), Path.of("/proc/self/exe"),
                Path.of(System.getProperty("java.home"), "bin", "java"));
            source = "linux_own_proc";
        }
        System.getLogger("UnifiedAdmission").log(System.Logger.Level.DEBUG,
            "Verified argument observation source=" + source + " count=" + args.size() + " sha256=" + digestStrings(args));
        return args;
    }
    static List<String> readLinuxCommandLine(Path commandLine, Path executable, Path javaExecutable) throws IOException {
        byte[] bytes;
        try (InputStream input = Files.newInputStream(commandLine)) { bytes = input.readNBytes(MAX_PROCESS_ARGUMENT_BYTES + 1); }
        return decodeLinuxCommandLine(bytes, executable.toRealPath(), javaExecutable.toRealPath());
    }
    static List<String> decodeLinuxCommandLine(byte[] bytes, Path actualExecutable, Path expectedJavaExecutable) throws IOException {
        if (bytes.length == 0 || bytes.length > MAX_PROCESS_ARGUMENT_BYTES || bytes[bytes.length - 1] != 0)
            throw new IOException("Malformed, unterminated or oversized own-process argument data");
        String text;
        try {
            text = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(java.nio.charset.CodingErrorAction.REPORT)
                .onUnmappableCharacter(java.nio.charset.CodingErrorAction.REPORT)
                .decode(java.nio.ByteBuffer.wrap(bytes)).toString();
        } catch (java.nio.charset.CharacterCodingException e) { throw new IOException("Own-process arguments are not valid UTF-8", e); }
        List<String> tokens = new ArrayList<>(Arrays.asList(text.split("\\x00", -1)));
        tokens.removeLast(); // Remove only the terminal separator; legitimate empty argv elements remain.
        if (tokens.isEmpty() || tokens.getFirst().isEmpty()) throw new IOException("Own-process argument data has no executable");
        Path declaredExecutable = Path.of(tokens.removeFirst());
        if (!declaredExecutable.isAbsolute() || !declaredExecutable.toRealPath().equals(actualExecutable.toRealPath())
            || !actualExecutable.toRealPath().equals(expectedJavaExecutable.toRealPath()))
            throw new IOException("Own-process executable does not match the active Java installation");
        return List.copyOf(tokens);
    }
    private static void verifyConsumer(Path path) throws IOException {
        // Capability is checked only after its exact installation origin and bytes were pinned.
        // This resource is never a trust grant for an external self-declared candidate.
        try (java.util.zip.ZipFile jar = new java.util.zip.ZipFile(path.toFile())) {
            if (jar.getEntry("org/sinytra/connector/infinity/FmlCompatibilityComponent.class") == null)
                throw new IOException("Pinned core has no explicit FML compatibility component");
            rejectAutonomousServices(jar);
            var entry = jar.getEntry("META-INF/unified-admission/consumer-v1.json");
            if (entry == null) throw new IOException("Pinned core lacks authoritative Session consumers");
            Consumer consumer;
            try (InputStream in = jar.getInputStream(entry)) {
                byte[] bytes = in.readNBytes(8193);
                if (bytes.length > 8192) throw new IOException("Oversized consumer capability metadata");
                consumer = new Gson().fromJson(new String(bytes, StandardCharsets.UTF_8), Consumer.class);
            }
            if (consumer == null || consumer.protocol() != 1 || !"fml_loader".equals(consumer.runtimeModelOwner())
                || consumer.consumers() == null || !consumer.consumers().containsAll(List.of("ConnectorLocator", "FabricModsDiscoverer", "OrdinaryAdmissionGate", "ManagedQuiltModules")))
                throw new IOException("Pinned core has an incompatible admission consumer protocol");
        }
    }
    private static final Set<String> OWNED_SERVICES = Set.of(
        "cpw.mods.modlauncher.api.ITransformationService",
        "net.neoforged.neoforgespi.locating.IModFileCandidateLocator",
        "net.neoforged.neoforgespi.locating.IModFileReader",
        "net.neoforged.neoforgespi.locating.IDependencyLocator",
        "net.neoforged.neoforgespi.language.IModLanguageLoader",
        "net.neoforged.neoforgespi.coremod.ICoreMod");
    private static void rejectAutonomousServices(java.util.zip.ZipFile jar) throws IOException {
        for (String service : OWNED_SERVICES) {
            var entry = jar.getEntry("META-INF/services/" + service);
            if (entry != null) try (InputStream in = jar.getInputStream(entry)) {
                byte[] bytes = in.readNBytes(65537);
                if (bytes.length > 65536) throw new IOException("Oversized autonomous service descriptor");
                if (new String(bytes, StandardCharsets.UTF_8).lines().map(line -> line.split("#", 2)[0].trim()).anyMatch(line -> !line.isEmpty()))
                    throw new IOException("Pinned compatibility component retains autonomous service " + service);
            }
        }
        for (var entries = jar.entries(); entries.hasMoreElements();) {
            var entry = entries.nextElement();
            if (entry.getName().equals("module-info.class") || entry.getName().matches("META-INF/versions/[0-9]+/module-info\\.class")) {
                try (InputStream in = jar.getInputStream(entry)) {
                    byte[] bytes = in.readNBytes(1024 * 1024 + 1);
                    if (bytes.length > 1024 * 1024) throw new IOException("Oversized installed module descriptor");
                    var descriptor = java.lang.module.ModuleDescriptor.read(new ByteArrayInputStream(bytes));
                    if (descriptor.provides().stream().anyMatch(provider -> OWNED_SERVICES.contains(provider.service())))
                        throw new IOException("Pinned compatibility module retains autonomous JPMS providers");
                }
            }
        }
    }
    private static void verifyGameComponent(Path path, String implementation) throws IOException {
        try (java.util.zip.ZipFile jar = new java.util.zip.ZipFile(path.toFile())) {
            if (jar.getEntry(implementation) == null || jar.getEntry("META-INF/neoforge.mods.toml") == null)
                throw new IOException("Installed GAME component lacks implementation or genuine capability metadata");
        }
    }
    static Path authorizedPath(Path installation, String relative) throws IOException {
        Path r = Path.of(relative);
        if (r.isAbsolute() || r.normalize().startsWith("..")) throw new IOException("Installation paths must be contained relative paths");
        Path actual = installation.resolve(r).toRealPath();
        if (!actual.startsWith(installation) || !Files.isRegularFile(actual)) throw new IOException("Installation origin escaped its permitted root");
        return actual;
    }
    static String sha256(Path path) throws IOException {
        MessageDigest digest = digest();
        try (InputStream in = Files.newInputStream(path)) { byte[] bytes = new byte[65536]; int n; while ((n = in.read(bytes)) >= 0) digest.update(bytes, 0, n); }
        return HexFormat.of().formatHex(digest.digest());
    }
    static void verify(Path path, String expected) throws IOException {
        if (expected == null || !expected.matches("[0-9a-f]{64}") || !sha256(path).equals(expected)) throw new IOException("Pinned input changed: " + path);
    }
    public static String digestStrings(List<String> values) {
        MessageDigest digest = digest();
        for (String value : values) {
            byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
            digest.update((bytes.length + "\n").getBytes(StandardCharsets.US_ASCII)); digest.update(bytes);
        }
        return HexFormat.of().formatHex(digest.digest());
    }
    private static MessageDigest digest() { try { return MessageDigest.getInstance("SHA-256"); } catch (NoSuchAlgorithmException impossible) { throw new AssertionError(impossible); } }
}
