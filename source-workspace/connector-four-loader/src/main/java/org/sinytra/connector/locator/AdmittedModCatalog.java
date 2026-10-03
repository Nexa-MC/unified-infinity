package org.sinytra.connector.locator;

import net.neoforged.neoforgespi.language.IModInfo;
import net.neoforged.fml.ModContainer;
import net.neoforged.neoforgespi.locating.IModFile;
import org.sinytra.connector.infinity.BuildIdentity;
import org.sinytra.connector.infinity.inventory.*;
import static org.sinytra.connector.infinity.inventory.AdmissionInventory.*;

import java.nio.file.Path;
import java.util.*;

/** The single catalog binding: capture intake once, then freeze against actual final host owners. */
public final class AdmittedModCatalog {
    private static final Map<InventoryReconciler.Key, Entry> CAPTURED = new HashMap<>();
    private static final List<Exclusion> EXCLUSIONS = new ArrayList<>();
    private static List<InventoryReconciler.Key> frozenOwners;
    private AdmittedModCatalog() {}
    public static synchronized Optional<Snapshot> snapshot() { return AdmissionSession.isInstalled() ? AdmissionSession.current().selectedSnapshot() : Optional.empty(); }
    public static Optional<AdmissionMetadata.Scan> scanned(Path path) { return AdmissionSession.current().scan(path); }
    public static synchronized void recordExclusions(List<Exclusion> exclusions) {
        ensureMutable(); for (Exclusion exclusion : exclusions) if (!EXCLUSIONS.contains(exclusion)) EXCLUSIONS.add(exclusion);
    }
    public static synchronized void capture(IModFile owner, Entry entry) {
        ensureMutable();
        InventoryReconciler.Key key = new InventoryReconciler.Key(owner, entry.canonicalId());
        Entry previous = CAPTURED.putIfAbsent(key, entry);
        if (previous != null && !previous.equals(entry)) throw new IllegalStateException("Conflicting admitted provenance for " + entry.canonicalId());
    }
    public static synchronized void captureOriginal(IModFile owner, Path input, Ecosystem ecosystem, Lane lane,
                                                     Optional<String> digest) {
        AdmissionMetadata.Scan scan = scanned(input).orElse(null);
        if (scan == null) return;
        for (IModInfo mod : owner.getModInfos()) {
            AdmissionMetadata.Mod original = scan.mods().stream()
                .filter(m -> canonical(m.id()).equals(mod.getModId()) || m.id().equals(mod.getModId())).findFirst().orElse(null);
            if (original == null) continue;
            capture(owner, entry(owner, mod, original, scan.candidate().source(), input, ecosystem, lane, digest));
        }
    }
    private static Entry entry(IModFile owner, IModInfo mod, AdmissionMetadata.Mod original, SourceChain source,
                               Path input, Ecosystem ecosystem, Lane lane, Optional<String> digest) {
        Optional<TrustedPayloads.Receipt> trusted = TrustedPayloads.find(input, List.of(original.id()));
        return new Entry(mod.getModId(), Optional.of(original.id()), original.name(),
            original.declaredVersion().filter(v -> !v.contains("${")), original.declaredVersion(), mod.getVersion().toString(),
            ecosystem, lane, trusted.map(TrustedPayloads.Receipt::category).orElse(Category.USER_MOD),
            trusted.flatMap(TrustedPayloads.Receipt::apiFamily), original.licenses(), new Provenance(
            List.of(trusted.map(TrustedPayloads.Receipt::source).orElse(source)), owner.getFilePath().toUri().toString(),
            trusted.map(TrustedPayloads.Receipt::sha256).or(() -> digest),
            trusted.isPresent() ? Evidence.MANAGED_PINNED_EXTRACTION : Evidence.ORIGINAL_INTAKE));
    }
    /** Supply the actual final host container, never a mod-ID guess. */
    public static synchronized void captureHostGame(ModContainer container) {
        if (!container.getClass().getName().equals("net.neoforged.fml.mclanguageprovider.MinecraftModContainer")
            || container.getClass().getModule() != ModContainer.class.getModule()) return;
        IModInfo mod = container.getModInfo();
        if (!mod.getModId().equals("minecraft")) throw new IllegalArgumentException("Unexpected host game container identity");
        IModFile owner = mod.getOwningFile().getFile();
        capture(owner, new Entry(mod.getModId(), Optional.of(mod.getModId()), mod.getDisplayName(),
            Optional.of(mod.getVersion().toString()), Optional.empty(), mod.getVersion().toString(), Ecosystem.UNKNOWN,
            Lane.GAME, Category.PLATFORM, Optional.empty(), licenses(owner),
            new Provenance(List.of(), owner.getFilePath().toUri().toString(), Optional.empty(), Evidence.SELECTED_HOST)));
    }
    /** Call once only after all final ModContainers exist. Repeated calls must have the same final owners/order. */
    public static synchronized Snapshot freeze(List<? extends IModInfo> finalMods) {
        Snapshot snapshot = snapshot().orElse(null);
        List<InventoryReconciler.Key> owners = finalMods.stream()
            .map(m -> new InventoryReconciler.Key(m.getOwningFile().getFile(), m.getModId())).toList();
        if (frozenOwners != null && !frozenOwners.equals(owners)) throw new IllegalStateException("Final host owners/order changed after freeze");
        List<InventoryReconciler.HostRow> rows = new ArrayList<>();
        for (IModInfo mod : finalMods) {
            IModFile owner = mod.getOwningFile().getFile();
            if (snapshot == null && !CAPTURED.containsKey(new InventoryReconciler.Key(owner, mod.getModId()))) {
                // Only a captured native descriptor earns native ecosystem/provenance. Unknowns stay honest.
                var scan = scanned(owner.getFilePath()).orElse(null);
                if (scan != null && scan.candidate().ecosystem() == Ecosystem.NEOFORGE)
                    captureOriginal(owner, owner.getFilePath(), Ecosystem.NEOFORGE, Lane.NATIVE_HOST, Optional.empty());
                else if (java.nio.file.Files.isRegularFile(owner.findResource("META-INF/neoforge.mods.toml")))
                    captureNativeSelected(owner, mod);
            }
            rows.add(new InventoryReconciler.HostRow(owner, mod.getModId(), mod.getDisplayName(), mod.getVersion().toString(), owner.getFilePath().toUri().toString()));
        }
        List<Exclusion> allExclusions = java.util.stream.Stream.concat(EXCLUSIONS.stream(),
            AdmissionSession.current().snapshot().stream().flatMap(entry -> entry.decision().exclusions().stream())).distinct().toList();
        Snapshot next = InventoryReconciler.reconcile(BuildIdentity.SOURCE_SHA256, rows, CAPTURED,
            InfrastructurePolicy.reconcileNotices(allExclusions, finalMods.stream().map(IModInfo::getModId).toList()));
        if (snapshot != null && !snapshot.equals(next)) throw new IllegalStateException("Final host inventory changed after freeze");
        AdmissionSession.current().publishSelected(next); frozenOwners = owners; return next;
    }
    private static void captureNativeSelected(IModFile owner, IModInfo mod) {
        Optional<String> declared = mod.getConfig().<Object>getConfigElement("version").map(Object::toString);
        Optional<TrustedPayloads.Receipt> trusted = TrustedPayloads.find(owner.getFilePath(), List.of(mod.getModId()));
        boolean direct = owner.getDiscoveryAttributes().parent() == null;
        // A JiJ filesystem root is a runtime location, not an original embedded entry. Do not fabricate it.
        List<SourceChain> sources = trusted.map(t -> List.of(t.source())).orElseGet(() -> direct
            ? List.of(OrdinaryAdmissionGate.root(owner.getFilePath())) : List.of());
        capture(owner, new Entry(mod.getModId(), Optional.of(mod.getModId()), mod.getDisplayName(),
            declared.filter(v -> !v.contains("${")), declared, mod.getVersion().toString(), Ecosystem.NEOFORGE,
            Lane.NATIVE_HOST, trusted.map(TrustedPayloads.Receipt::category).orElse(direct ? Category.USER_MOD : Category.UNKNOWN),
            trusted.flatMap(TrustedPayloads.Receipt::apiFamily), List.of(), new Provenance(sources, owner.getFilePath().toUri().toString(),
            trusted.map(TrustedPayloads.Receipt::sha256), trusted.isPresent() ? Evidence.MANAGED_PINNED_EXTRACTION : Evidence.SELECTED_HOST)));
    }
    private static List<String> licenses(IModFile owner) {
        String license = owner.getModFileInfo().getLicense();
        return license == null || license.isBlank() ? List.of() : List.of(license);
    }
    private static void ensureMutable() { if (snapshot().isPresent()) throw new IllegalStateException("Admission inventory is frozen"); }
    private static Path key(Path path) { return path.toAbsolutePath().normalize(); }
    private static String canonical(String original) {
        String value = original.replace('-', '_');
        return org.sinytra.connector.util.ConnectorUtil.isJavaReservedKeyword(value) ? value + "_nojpms" : value;
    }
}
