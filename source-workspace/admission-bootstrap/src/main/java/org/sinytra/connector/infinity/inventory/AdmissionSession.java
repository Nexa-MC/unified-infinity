package org.sinytra.connector.infinity.inventory;

import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.zip.*;
import static org.sinytra.connector.infinity.inventory.AdmissionInventory.*;

/** Single BOOT-owned frozen metadata transaction. Derived aliases never create a new policy decision. */
public final class AdmissionSession {
    private static volatile AdmissionSession installed;
    private static boolean initializing;
    private static final int MAX_ARCHIVES = 4096, MAX_DEPTH = 8, MAX_ENTRIES = 65536;
    private static final long MAX_NESTED_BYTES = 32L * 1024 * 1024, MAX_TOTAL_NESTED_BYTES = 256L * 1024 * 1024;
    public record Entry(Path path, String sha256, long size, AdmissionMetadata.Scan scan,
                        InfrastructurePolicy.Decision decision, List<Path> children) {
        public Entry { children = List.copyOf(children); }
    }
    private final Path game, mods;
    private final String target;
    private final Map<Path, Entry> entries;
    private final Map<String, Path> nested;
    private final List<Path> folder;
    private final Set<Path> trustedOrigins;
    private final Map<String, List<Path>> installedRoles;
    private final Map<Path, Alias> aliases = new ConcurrentHashMap<>();
    private final Map<Path, List<Path>> generatedInputs = new ConcurrentHashMap<>();
    private volatile AdmissionInventory.Snapshot selectedInventory;
    private final Map<Module, Path> installedModuleOwners = Collections.synchronizedMap(new IdentityHashMap<>());
    private final Set<String> emitted = ConcurrentHashMap.newKeySet();
    private final Map<Object, List<Path>> runtimeObjects = Collections.synchronizedMap(new IdentityHashMap<>());
    private record Alias(Path origin, String sha256) {}
    private AdmissionSession(Builder b) {
        game = b.game; mods = b.mods; target = b.policy.launchTarget(); entries = Map.copyOf(b.entries);
        nested = Map.copyOf(b.nested); folder = List.copyOf(b.folder); trustedOrigins = Set.copyOf(b.trustedOrigins);
        Map<String, List<Path>> roles = new HashMap<>();
        for (var artifact : b.policy.artifacts()) roles.computeIfAbsent(artifact.role(), ignored -> new ArrayList<>()).add(key(b.installation.resolve(artifact.path())));
        roles.replaceAll((role, paths) -> List.copyOf(paths)); installedRoles = Map.copyOf(roles);
    }
    public static boolean isInstalled() { return installed != null; }
    public static AdmissionSession current() {
        AdmissionSession result = installed;
        if (result == null) throw new IllegalStateException("Unified admission was not initialized before discovery");
        return result;
    }
    static synchronized AdmissionSession initialize(BootstrapInstallation.Policy policy) throws IOException {
        if (installed != null || initializing) throw new IllegalStateException("Admission initialization may occur only once");
        initializing = true;
        TrustedPayloads.beginRegistration();
        AdmissionSession result;
        try {
            Builder builder = new Builder(policy); builder.build();
            result = new AdmissionSession(builder);
        } finally {
            TrustedPayloads.sealRegistration();
            // A failed partial initialization is terminal. Never reuse a partially populated receipt registry.
        }
        installed = result;
        for (Entry entry : result.entries.values()) result.notice(entry);
        return result;
    }

    public void requireLaunch(Path directory, String launchTarget) throws IOException {
        if (!game.equals(directory.toRealPath()) || !Objects.equals(target, launchTarget)) throw new IOException("Admission launch epoch changed");
    }
    public Optional<AdmissionMetadata.Scan> scan(Path path) { return entry(path).map(Entry::scan); }
    public Optional<InfrastructurePolicy.Decision> decision(Path path) { return entry(path).map(Entry::decision); }
    public void requireKnown(Path path) { requireEntry(path); }
    /** Installation-owned roots only; ordinary user folders cannot contribute internal loader components. */
    public List<Path> installedComponents(String role) {
        List<Path> paths = installedRoles.getOrDefault(role, List.of());
        if (!paths.isEmpty() && !permits(paths)) throw new IllegalStateException("Installed component was excluded by admission");
        return paths;
    }
    public Path installedComponent(String role) {
        List<Path> paths = installedComponents(role);
        if (paths.size() != 1) throw new IllegalStateException("Expected exactly one installed " + role + " component");
        return paths.getFirst();
    }
    public Optional<AdmissionInventory.Snapshot> selectedSnapshot() { return Optional.ofNullable(selectedInventory); }
    public synchronized void publishSelected(AdmissionInventory.Snapshot snapshot) {
        Class<?> caller = trustedCaller();
        if (!caller.getName().equals("org.sinytra.connector.locator.AdmittedModCatalog"))
            throw new IllegalStateException("Only the pinned final host catalog can publish selected inventory");
        Objects.requireNonNull(snapshot);
        if (selectedInventory != null && !selectedInventory.equals(snapshot))
            throw new IllegalStateException("Selected inventory has already been frozen");
        selectedInventory = snapshot;
    }
    public List<Entry> snapshot() { return entries.values().stream().sorted(Comparator.comparing(e -> e.path().toString())).toList(); }
    public List<Path> admittedFolder(Path directory) {
        if (!directory.toAbsolutePath().normalize().equals(mods)) throw new IllegalStateException("Unsupported discovery folder " + directory);
        return folder.stream().filter(path -> permits(List.of(path))).toList();
    }
    public boolean permits(List<Path> paths) {
        if (paths.isEmpty()) throw new IllegalStateException("Empty candidate group");
        boolean all = true;
        for (Path path : paths) {
            Entry entry = requireEntry(path); assertUnchanged(path, entry);
            List<Path> inputs = generatedInputs.get(key(path));
            if (inputs != null && !permits(inputs)) return false;
            if (entry.decision().action() == InfrastructurePolicy.Action.BLOCK_MIXED_FILE)
                throw new IllegalStateException("Unsupported mixed infrastructure/content container " + entry.scan().candidate().source());
            all &= entry.decision().mayExecute(); notice(entry);
        }
        return all;
    }
    /** FML binds actual SERVICE/GAME module identity after checking its module reference and class source. */
    public void bindInstalledModule(Module module, Path origin) {
        Class<?> caller = StackWalker.getInstance(StackWalker.Option.RETAIN_CLASS_REFERENCE).getCallerClass();
        if (caller.getModule() != AdmissionSession.class.getModule() || !"fml_loader".equals(caller.getModule().getName()))
            throw new IllegalStateException("Only the BOOT FML owner may bind installed layer modules");
        Path actual = key(origin);
        boolean installed = java.util.stream.Stream.of("ADMISSION_CONSUMER", "COMPATIBILITY_GAME", "PRODUCT_GAME")
            .flatMap(role -> installedRoles.getOrDefault(role, List.of()).stream()).anyMatch(actual::equals);
        if (!installed || !module.isNamed() || !permits(List.of(actual))) throw new IllegalStateException("Invalid installed module origin");
        synchronized (installedModuleOwners) {
            Path previous = installedModuleOwners.putIfAbsent(module, actual);
            if (previous != null && !previous.equals(actual)) throw new IllegalStateException("Installed module origin changed");
        }
    }
    /** Exact parent/entry lookup from the frozen scan, useful before opening a JiJ filesystem. */
    public Optional<Path> nestedArchive(Path parent, String entry) {
        Entry origin = requireEntry(parent);
        if (!permits(List.of(parent))) return Optional.empty();
        Path child = nested.get(nestedKey(origin.path(), entry));
        if (child == null) throw new IllegalStateException("Unrecorded nested origin " + entry);
        return permits(List.of(child)) ? Optional.of(child) : Optional.empty();
    }
    /** Trusted extraction adds a byte-proved alias only; it never rescans or grants origin trust by digest alone. */
    public void bindNested(Path extracted, Path parent, String exactEntry) {
        requireTrustedCaller();
        Path child = nestedArchive(parent, exactEntry).orElseThrow(() -> new IllegalStateException("Denied nested origin"));
        Entry record = requireEntry(child); bind(extracted, record, record.sha256());
        if (TrustedPayloads.find(record.path(), record.scan().candidate().primaryIds()).isPresent()) {
            try { TrustedPayloads.bindPinnedCopy(record.path(), key(extracted)); }
            catch (IOException e) { throw new UncheckedIOException(e); }
        }
    }
    /** Transformed bytes retain the admitted original's identity, and require the pinned Connector implementation. */
    public void bindDerived(Path transformed, Path original) {
        Class<?> caller = trustedCaller();
        if (!caller.getName().startsWith("org.sinytra.connector.")) throw new IllegalStateException("Untrusted transformation authority");
        if (!permits(List.of(original))) throw new IllegalStateException("Transformation from denied origin");
        Entry entry = requireEntry(original);
        try { bind(transformed, entry, BootstrapInstallation.sha256(transformed)); }
        catch (IOException e) { throw new UncheckedIOException(e); }
    }
    /** Existing Connector-generated support code only. This creates no mod/API provider or new policy decision. */
    public void bindGenerated(Path output, List<Path> admittedSourceInputs) {
        Class<?> caller = trustedCaller();
        if (!caller.getName().startsWith("org.sinytra.connector.")) throw new IllegalStateException("Untrusted generation authority");
        if (!permits(admittedSourceInputs)) throw new IllegalStateException("Generated output includes denied origins");
        try (ZipFile zip = new ZipFile(output.toFile())) {
            for (String metadata : List.of("fabric.mod.json", "quilt.mod.json", "META-INF/mods.toml", "META-INF/neoforge.mods.toml"))
                if (zip.getEntry(metadata) != null) throw new IOException("Generated support output declares a mod provider");
            for (var iterator = zip.entries(); iterator.hasMoreElements();) {
                String name = iterator.nextElement().getName();
                if (name.startsWith("META-INF/services/") || name.endsWith("module-info.class"))
                    throw new IOException("Generated support output declares service/module metadata");
            }
            List<Path> inputs = admittedSourceInputs.stream().map(AdmissionSession::key).distinct().toList();
            Path actual = output.toRealPath();
            if (inputs.contains(actual)) throw new IOException("Generated output cannot be its own input");
            bind(actual, requireEntry(inputs.getFirst()), BootstrapInstallation.sha256(actual));
            List<Path> previous = generatedInputs.putIfAbsent(actual, inputs);
            if (previous != null && !previous.equals(inputs)) throw new IOException("Conflicting generated input origins");
        } catch (IOException e) { throw new UncheckedIOException(e); }
    }
    /** Internal receipt for grouped host objects; primary-path-only inference is deliberately forbidden. */
    public void bindRuntimeObject(Object object, List<Path> paths) {
        requireTrustedCaller();
        if (!permits(paths)) throw new IllegalStateException("Runtime object contains a denied origin");
        List<Path> frozen = paths.stream().map(AdmissionSession::key).toList();
        synchronized (runtimeObjects) {
            List<Path> previous = runtimeObjects.putIfAbsent(Objects.requireNonNull(object), frozen);
            if (previous != null && !previous.equals(frozen)) throw new IllegalStateException("Conflicting runtime object provenance");
        }
    }
    public List<Path> sourcePathsForRuntimeObject(Object object) {
        List<Path> paths = runtimeObjects.get(object);
        if (paths == null) throw new IllegalStateException("Runtime object has no frozen provenance");
        return paths;
    }
    public boolean permitsRuntimeObject(Object object) {
        List<Path> paths = runtimeObjects.get(object);
        if (paths == null) throw new IllegalStateException("Unrecorded direct/grouped runtime object; use the frozen admission origin");
        return permits(paths);
    }
    public void inheritRuntimeObject(Object targetObject, Object sourceObject) {
        requireTrustedCaller();
        List<Path> paths = runtimeObjects.get(sourceObject);
        if (paths == null) throw new IllegalStateException("Runtime object source has no provenance receipt");
        List<Path> existing = runtimeObjects.get(targetObject);
        if (existing != null) {
            Set<Path> sourceOrigins = new HashSet<>(), targetOrigins = new HashSet<>();
            for (Path path : paths) sourceOrigins.add(requireEntry(path).path());
            for (Path path : existing) targetOrigins.add(requireEntry(path).path());
            if (!sourceOrigins.equals(targetOrigins) || !permits(existing) || !permits(paths))
                throw new IllegalStateException("Returned reader object changed the complete source origin set");
            return; // Preserve the verified transformed bytes, not an unverified primary-path substitution.
        }
        bindRuntimeObject(targetObject, paths);
    }
    private void bind(Path output, Entry origin, String expected) {
        try {
            Path actual = output.toRealPath();
            if (!Files.isRegularFile(actual)) throw new IOException("Runtime directory roots require explicit host object receipts");
            BootstrapInstallation.verify(actual, expected);
            if (entries.containsKey(actual)) {
                if (!actual.equals(origin.path())) throw new IOException("Derived path overwrites another frozen origin");
                return;
            }
            Alias value = new Alias(origin.path(), expected), previous = aliases.putIfAbsent(actual, value);
            if (previous != null && !previous.equals(value)) throw new IOException("Conflicting derived origin");
        } catch (IOException e) { throw new UncheckedIOException(e); }
    }
    private void requireTrustedCaller() { trustedCaller(); }
    private Class<?> trustedCaller() {
        Class<?> caller = StackWalker.getInstance(StackWalker.Option.RETAIN_CLASS_REFERENCE).walk(frames -> frames
            .map(StackWalker.StackFrame::getDeclaringClass).filter(type -> type != AdmissionSession.class).findFirst().orElseThrow());
        if (caller.getModule() == AdmissionSession.class.getModule()) return caller;
        Path owner = installedModuleOwners.get(caller.getModule());
        if (owner == null || !permits(List.of(owner)))
            throw new IllegalStateException("Caller is not an FML-bound installed module authority");
        return caller;
    }
    private Optional<Entry> entry(Path path) {
        Path actual = key(path); Entry direct = entries.get(actual);
        if (direct != null) return Optional.of(direct);
        Alias alias = aliases.get(actual); return Optional.ofNullable(alias == null ? null : entries.get(alias.origin()));
    }
    private Entry requireEntry(Path path) { return entry(path).orElseThrow(() -> new IllegalStateException("Unrecorded admission origin " + path)); }
    private void assertUnchanged(Path path, Entry entry) {
        try {
            Path actual = path.toRealPath(); Alias alias = aliases.get(actual);
            BootstrapInstallation.verify(actual, alias == null ? entry.sha256() : alias.sha256());
        } catch (IOException e) { throw new UncheckedIOException("Admission bytes changed; restart with a new session", e); }
    }
    private void notice(Entry entry) {
        for (Exclusion exclusion : entry.decision().exclusions()) {
            String key = exclusion.source() + "|" + exclusion.originalId() + "|" + exclusion.ruleId();
            if (emitted.add(key)) System.getLogger("UnifiedAdmission").log(System.Logger.Level.WARNING,
                "External " + exclusion.originalId() + " excluded before service selection: " + exclusion.reason()
                    + "; source=" + exclusion.source() + "; original archive unchanged");
        }
    }
    private static Path key(Path path) { try { return path.toRealPath(); } catch (IOException e) { throw new UncheckedIOException(e); } }
    private static String nestedKey(Path parent, String entry) { return parent + "\n" + entry; }

    private static final class Builder {
        final BootstrapInstallation.Policy policy;
        final Path game, mods, cache, installation;
        final Map<Path, Entry> entries = new LinkedHashMap<>();
        final Map<String, Path> nested = new LinkedHashMap<>();
        final List<Path> folder = new ArrayList<>();
        final Set<Path> trustedOrigins = new HashSet<>();
        final Map<Path, TrustedPayloads.Root> roots = new HashMap<>();
        long nestedBytes;
        int archives;
        Builder(BootstrapInstallation.Policy policy) throws IOException {
            this.policy = policy; game = Path.of(policy.gameDirectory()).toRealPath();
            mods = game.resolve("mods").toAbsolutePath().normalize();
            installation = Path.of(policy.installationDirectory()).toRealPath();
            // Only new session-owned copies are written; existing mods/managed archives are never rewritten.
            cache = Files.createTempDirectory("unified-admission-");
        }
        void build() throws IOException {
            for (BootstrapInstallation.Artifact artifact : policy.artifacts()) {
                Path path = BootstrapInstallation.authorizedPath(installation, artifact.path());
                String expected = artifact.role().equals("BOOT_OWNER") ? BootstrapInstallation.sha256(path) : artifact.sha256();
                roots.put(path, TrustedPayloads.registerRoot(path, expected, Set.copyOf(artifact.primaryIds())));
                trustedOrigins.add(path);
            }
            for (BootstrapInstallation.Artifact artifact : policy.artifacts()) {
                Path path = BootstrapInstallation.authorizedPath(installation, artifact.path());
                Entry root = scanTree(path, new SourceChain(path.toString(), List.of()), 0);
                if (!Set.copyOf(artifact.primaryIds()).equals(Set.copyOf(root.scan().candidate().primaryIds())))
                    throw new IOException("Installed root descriptor IDs differ from authoritative pins: " + artifact.path());
            }
            if (Files.exists(mods)) {
                if (!Files.isDirectory(mods) || Files.isSymbolicLink(mods)) throw new IOException("Unsupported mods directory origin");
                try (var stream = Files.list(mods)) {
                    for (Path path : stream.sorted().toList()) if (path.getFileName().toString().toLowerCase(Locale.ROOT).endsWith(".jar")) {
                        if (!Files.isRegularFile(path) || Files.isSymbolicLink(path)) throw new IOException("Unsupported mod path " + path);
                        Path actual = path.toRealPath(); folder.add(actual);
                        scanTree(actual, new SourceChain(actual.toString(), List.of()), 0);
                    }
                }
            }
        }
        Entry scanTree(Path input, SourceChain source, int depth) throws IOException {
            Path path = input.toRealPath(); Entry old = entries.get(path); if (old != null) return old;
            if (++archives > MAX_ARCHIVES || depth > MAX_DEPTH) throw new IOException("Admission archive/depth bound exceeded");
            String before = BootstrapInstallation.sha256(path);
            AdmissionMetadata.Scan scan = AdmissionMetadata.scan(path, source);
            // Authoritative pins match origin chain and expected bytes, not metadata claims or matching IDs elsewhere.
            if (!source.embeddedEntries().isEmpty()) registerManaged(path, source, scan);
            InfrastructurePolicy.Decision decision = InfrastructurePolicy.evaluate(scan.candidate());
            if (decision.action() == InfrastructurePolicy.Action.REQUIRE_PRE_SERVICE_GATE)
                decision = new InfrastructurePolicy.Decision(decision.unrelatedIds().isEmpty() ? InfrastructurePolicy.Action.EXCLUDE
                    : InfrastructurePolicy.Action.BLOCK_MIXED_FILE, decision.exclusions(), decision.unrelatedIds());
            List<Path> children = new ArrayList<>();
            List<AuditedConnectorEnvelope.Nested> envelopeChildren = new ArrayList<>();
            try (ZipFile zip = new ZipFile(path.toFile())) {
                if (zip.size() > MAX_ENTRIES) throw new IOException("Admission archive entry-count bound exceeded");
                Set<String> names = new HashSet<>();
                for (var e = zip.entries(); e.hasMoreElements();) if (!names.add(e.nextElement().getName())) throw new IOException("Duplicate archive entry");
                for (String name : scan.declaredNestedJars()) {
                    var entry = zip.getEntry(name);
                    if (entry == null || entry.isDirectory() || entry.getSize() > MAX_NESTED_BYTES) throw new IOException("Missing/oversized declared nested archive " + name);
                    Path child = Files.createTempFile(cache, "nested-", ".jar");
                    long count = 0;
                    try (InputStream in = zip.getInputStream(entry); OutputStream out = Files.newOutputStream(child)) {
                        byte[] bytes = new byte[65536]; int n;
                        while ((n = in.read(bytes)) >= 0) {
                            count += n; nestedBytes += n;
                            if (count > MAX_NESTED_BYTES || nestedBytes > MAX_TOTAL_NESTED_BYTES) throw new IOException("Admission decompressed byte bound exceeded");
                            out.write(bytes, 0, n);
                        }
                    }
                    Entry childRecord = scanTree(child, source.nested(name), depth + 1);
                    children.add(childRecord.path()); nested.put(nestedKey(path, name), childRecord.path());
                    envelopeChildren.add(new AuditedConnectorEnvelope.Nested(name, childRecord.sha256(),
                        childRecord.scan().candidate().primaryIds(), childRecord.scan().candidate().earlyServiceProvider()));
                    // A nested JAR is a separately admitted loader candidate, not executable parent code.
                    // Preserve ordinary content parents; all declared child edges still consult this session.
                    // Service-bearing parents with denied children have ambiguous early ownership in this first profile.
                    if (!childRecord.decision().mayExecute() && decision.mayExecute() && scan.candidate().earlyServiceProvider())
                        decision = new InfrastructurePolicy.Decision(InfrastructurePolicy.Action.BLOCK_MIXED_FILE,
                            childRecord.decision().exclusions(), scan.candidate().primaryIds());
                }
                // One exact audited upstream bridge envelope may be excluded as a whole. A digest never grants admission.
                // Keep the canonical child exclusion/source chain; all other ambiguous service containers still fail closed.
                if (!trustedOrigins.contains(path) && decision.action() == InfrastructurePolicy.Action.BLOCK_MIXED_FILE
                    && AuditedConnectorEnvelope.matches(before, scan, zip, envelopeChildren))
                    decision = new InfrastructurePolicy.Decision(InfrastructurePolicy.Action.EXCLUDE, decision.exclusions(), List.of());
                // The reverse nesting direction is not safe to silently skip: excluding an API envelope
                // must not hide a separately declared, otherwise admitted content mod/provider beneath it.
                if (decision.action() == InfrastructurePolicy.Action.EXCLUDE) {
                    Set<String> retainedIds = new LinkedHashSet<>();
                    boolean retained = false;
                    for (Path child : children) retained |= collectRetainedDescendants(entries.get(child), retainedIds);
                    if (retained) decision = new InfrastructurePolicy.Decision(InfrastructurePolicy.Action.BLOCK_MIXED_FILE,
                        decision.exclusions(), List.copyOf(retainedIds));
                }
            }
            if (decision.mayExecute()) {
                try (ZipFile zip = new ZipFile(path.toFile())) {
                    boolean ownsPackage = zip.stream().anyMatch(e -> e.getName().startsWith("org/sinytra/connector/infinity/inventory/") && e.getName().endsWith(".class"));
                    boolean isOwner = policy.artifacts().stream().anyMatch(a -> a.role().equals("BOOT_OWNER") && installation.resolve(a.path()).normalize().equals(path));
                    if (ownsPackage && !isOwner) throw new IOException("Duplicate BOOT admission package owner: " + source);
                }
            }
            BootstrapInstallation.verify(path, before);
            Entry result = new Entry(path, before, Files.size(path), scan, decision, children); entries.put(path, result); return result;
        }
        boolean collectRetainedDescendants(Entry entry, Set<String> ids) {
            boolean retained = entry.decision().action() == InfrastructurePolicy.Action.BLOCK_MIXED_FILE;
            if (retained) ids.addAll(entry.decision().unrelatedIds());
            if (entry.decision().mayExecute()) {
                ids.addAll(entry.scan().candidate().primaryIds());
                retained |= !entry.scan().candidate().primaryIds().isEmpty() || entry.scan().candidate().earlyServiceProvider();
            }
            for (Path child : entry.children()) retained |= collectRetainedDescendants(entries.get(child), ids);
            return retained;
        }
        void registerManaged(Path path, SourceChain source, AdmissionMetadata.Scan scan) throws IOException {
            for (BootstrapInstallation.Embedded pin : policy.embedded()) {
                Path root = BootstrapInstallation.authorizedPath(installation, pin.root());
                if (!root.toString().equals(source.installationRoot()) || !pin.entries().equals(source.embeddedEntries())) continue;
                if (!Set.copyOf(pin.primaryIds()).equals(Set.copyOf(scan.candidate().primaryIds()))) throw new IOException("Managed descriptor IDs differ from installation pins");
                Category role = Category.valueOf(pin.role());
                TrustedPayloads.registerExtracted(roots.get(root), path, pin.entries(), pin.sha256(), Set.copyOf(pin.primaryIds()), role, Optional.ofNullable(pin.apiFamily()));
                trustedOrigins.add(path);
                return;
            }
        }
    }
}
