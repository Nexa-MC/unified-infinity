package org.sinytra.connector.infinity.inventory;

import java.nio.file.*;
import java.security.*;
import java.util.*;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;
import static org.sinytra.connector.infinity.inventory.AdmissionInventory.*;
import static org.sinytra.connector.infinity.inventory.InfrastructurePolicy.*;

/** Executable pure-JVM model tests. Not a substitute for host SERVICE/client acceptance. */
public final class AdmissionInventoryTest {
    private static int checks;
    public static void main(String[] args) throws Exception {
        Path temp = Files.createTempDirectory("admission-inventory-test-");
        try {
            policyDoesNotInventProviders(temp);
            TrustedPayloads.beginRegistration();
            managedOriginRequiresExactPathAndPin(temp);
            TrustedPayloads.sealRegistration();
            expect(IllegalStateException.class, () -> TrustedPayloads.registerRoot(temp.resolve("late.jar"), "0".repeat(64), Set.of("late")));
            reconcileOnlyFinalOwners();
            immutableCountsSearchAndRawVersions();
            displayProjectionPreservesActualMods();
            System.out.println("PASS " + checks + " admission inventory assertions (model only; no host launch)");
        } finally {
            try (var files = Files.walk(temp)) {
                for (Path path : files.sorted(Comparator.reverseOrder()).toList()) Files.delete(path);
            }
        }
    }
    private static void policyDoesNotInventProviders(Path temp) {
        check(evaluate(candidate(temp, Ecosystem.FABRIC, "fabric-api")).action() == Action.EXCLUDE, "external Fabric API skipped");
        check(evaluate(candidate(temp, Ecosystem.NEOFORGE, "fabric_api", "forgified_fabric_api")).action() == Action.EXCLUDE, "native multi-record FFAPI skipped");
        check(evaluate(candidate(temp, Ecosystem.FABRIC, "fabric-api", "valuable_content")).action() == Action.BLOCK_MIXED_FILE, "never silently suppress unrelated content");
        check(evaluate(candidate(temp, Ecosystem.FABRIC, "architectury")).mayExecute(), "ordinary Architectury allowed");
        check(evaluate(candidate(temp, Ecosystem.FABRIC, "cloth-config")).mayExecute(), "ordinary Cloth Config allowed");
        check(evaluate(candidate(temp, Ecosystem.FABRIC, "fabric_future_content")).mayExecute(), "no prefix blocklist");
        check(evaluate(candidate(temp, Ecosystem.QUILT, "quilt_future_content")).mayExecute(), "no Quilt prefix blocklist");
        Candidate ordinary = candidate(temp, Ecosystem.NEOFORGE, "connector");
        Decision early = evaluate(new Candidate(ordinary.path(), ordinary.source(), ordinary.ecosystem(), ordinary.primaryIds(), true));
        check(early.action() == Action.REQUIRE_PRE_SERVICE_GATE, "early SPI cannot be claimed as ordinary safe skip");
        check(!early.mayExecute(), "rule hit cannot run through policy callback");
        Decision unsupported = evaluate(candidate(temp, Ecosystem.QUILT, "quilt_resource_loader"));
        check(unsupported.action() == Action.EXCLUDE && unsupported.exclusions().getFirst().replacement() == Replacement.NO_API_REPLACEMENT,
            "unsupported exact QSL API excluded without inventing a replacement");
        Decision qsl = evaluate(candidate(temp, Ecosystem.QUILT, "quilt_base"));
        List<Exclusion> missing = reconcileNotices(qsl.exclusions(), Set.of("quilt_lifecycle_events"));
        check(missing.getFirst().replacement() == Replacement.NOT_VERIFIED, "different QSL module does not satisfy base");
        check(missing.getFirst().selectedReplacementIds().isEmpty(), "no synthetic dependency providers");
        check(reconcileNotices(qsl.exclusions(), Set.of("quilt_base")).getFirst().replacement() == Replacement.SELECTED_PROVIDER_PRESENT,
            "presence stays distinct from required version/API satisfaction");
    }
    private static void managedOriginRequiresExactPathAndPin(Path temp) throws Exception {
        Path payload = Files.writeString(temp.resolve("managed.jar"), "pinned api");
        Path root = temp.resolve("host.jar");
        try (ZipOutputStream archive = new ZipOutputStream(Files.newOutputStream(root))) {
            archive.putNextEntry(new ZipEntry("META-INF/jarjar/api.jar"));
            archive.write(Files.readAllBytes(payload)); archive.closeEntry();
        }
        Path external = Files.copy(payload, temp.resolve("copied-api.jar"));
        String hostPin = hash(root), apiPin = hash(payload);
        expect(java.io.IOException.class, () -> TrustedPayloads.registerRoot(root, "0".repeat(64), Set.of("host")));
        TrustedPayloads.Root origin = TrustedPayloads.registerRoot(root, hostPin, Set.of("host"));
        expect(java.io.IOException.class, () -> TrustedPayloads.registerExtracted(origin, payload, List.of("forged/path.jar"), apiPin, Set.of("fabric-api"), "FFAPI"));
        TrustedPayloads.registerExtracted(origin, payload, List.of("META-INF/jarjar/api.jar"), apiPin, Set.of("fabric-api"), "FFAPI");
        check(TrustedPayloads.find(payload, List.of("fabric-api")).isPresent(), "registered pinned extraction trusted");
        check(TrustedPayloads.find(external, List.of("fabric-api")).isEmpty(), "replayed digest at external path not trusted");
        check(TrustedPayloads.find(payload, List.of("forged_builtin_id")).isEmpty(), "forged builtin ID cannot reuse origin");
        check(TrustedPayloads.root(external).isEmpty(), "copied bytes cannot forge root");
        check(evaluate(new Candidate(payload, new SourceChain("claimed-external-host", List.of()), Ecosystem.FABRIC, List.of("fabric-api"), false)).mayExecute(),
            "only verified registry confers exemption, metadata source strings do not");
        check(evaluate(new Candidate(external, new SourceChain(root.toString(), List.of("META-INF/jarjar/api.jar")), Ecosystem.FABRIC, List.of("fabric-api"), false)).action() == Action.EXCLUDE,
            "forged source chain receives no builtin exemption");
        Files.writeString(payload, "changed api");
        check(TrustedPayloads.find(payload, List.of("fabric-api")).isEmpty(), "changed bytes cannot reuse an old exact-path receipt");
        Files.writeString(root, "changed root");
        check(TrustedPayloads.root(root).isEmpty(), "changed root invalidates root receipt");
    }
    private static void reconcileOnlyFinalOwners() {
        Object loser = new Object(), winner = new Object();
        Entry losing = entry("optab", "Op Tab", "2.0.0V1.21.1+1.21", Category.USER_MOD);
        Map<InventoryReconciler.Key, Entry> captures = Map.of(new InventoryReconciler.Key(loser, "optab"), losing);
        Snapshot result = InventoryReconciler.reconcile("test", List.of(new InventoryReconciler.HostRow(winner, "optab", "Actual host name", "2", "/selected.jar")), captures, List.of());
        check(result.entries().size() == 1 && result.counts().unknown() == 1, "losing candidate cannot replace selected owner");
        check(result.entries().getFirst().originalId().isEmpty(), "mismatched owner cannot inherit provenance");
        Snapshot empty = InventoryReconciler.reconcile("test", List.of(), captures, List.of());
        check(empty.entries().isEmpty(), "unselected/side-only candidates absent");
        expect(IllegalArgumentException.class, () -> InventoryReconciler.reconcile("test", List.of(
            new InventoryReconciler.HostRow(winner, "optab", "a", "1", "a"),
            new InventoryReconciler.HostRow(loser, "optab", "b", "2", "b")), captures, List.of()));
    }
    private static void immutableCountsSearchAndRawVersions() {
        List<Entry> mutable = new ArrayList<>(List.of(entry("farmersdelight", "Farmer's Delight", "1.2.9", Category.USER_MOD),
            entry("lithium", "Lithium", "0.15.4+mc1.21.1", Category.USER_MOD), entry("quilt_base", "QSL Base", "10.0.0-alpha.5+1.21.1", Category.BUNDLED_API),
            entry("minecraft", "Minecraft", "1.21.1", Category.PLATFORM), entry("unknown", "Unknown", "1", Category.UNKNOWN)));
        Snapshot snapshot = new Snapshot(1, "test", mutable, Counts.of(mutable), List.of()); mutable.clear();
        check(snapshot.entries().size() == 5 && snapshot.counts().total() == 5, "category totals exactly final rows");
        check(snapshot.search("FARMERSDELIGHT").size() == 1, "case-insensitive ID search");
        check(snapshot.search("farmer's").size() == 1, "name search");
        check(snapshot.entries().get(1).sourceVersion().orElseThrow().contains("+"), "raw original version preserved");
        expect(UnsupportedOperationException.class, () -> snapshot.entries().clear());
        expect(IllegalArgumentException.class, () -> new Snapshot(1, "test", snapshot.entries(), new Counts(0, 0, 0, 0), List.of()));
        expect(IllegalArgumentException.class, () -> new SourceChain("/a.jar", List.of("../escape.jar")));
    }
    private static void displayProjectionPreservesActualMods() {
        List<Entry> entries = new ArrayList<>();
        entries.add(displayEntry("farmersdelight", "Farmer's Delight", Ecosystem.NEOFORGE, Lane.NATIVE_HOST, Category.USER_MOD, Evidence.ORIGINAL_INTAKE));
        entries.add(displayEntry("clumps", "Clumps", Ecosystem.FORGE, Lane.FORGE_ADAPTER, Category.USER_MOD, Evidence.ORIGINAL_INTAKE));
        entries.add(displayEntry("lithium", "Lithium", Ecosystem.FABRIC, Lane.FABRIC_PROJECTION, Category.USER_MOD, Evidence.ORIGINAL_INTAKE));
        entries.add(displayEntry("chunky", "Chunky", Ecosystem.FABRIC, Lane.FABRIC_PROJECTION, Category.USER_MOD, Evidence.ORIGINAL_INTAKE));
        entries.add(displayEntry("optab", "Op Tab", Ecosystem.QUILT, Lane.NATIVE_QUILT, Category.USER_MOD, Evidence.ORIGINAL_INTAKE));
        for (int i = 0; i < 44; i++) entries.add(displayEntry("ffapi_fixture_" + i, "FFAPI fixture", Ecosystem.NEOFORGE, Lane.NATIVE_HOST, Category.BUNDLED_API, Evidence.MANAGED_PINNED_EXTRACTION));
        for (String id : List.of("quilt_base", "quilt_lifecycle_events")) entries.add(displayEntry(id, "QSL fixture", Ecosystem.QUILT, Lane.NATIVE_QUILT, Category.BUNDLED_API, Evidence.MANAGED_PINNED_EXTRACTION));
        Snapshot canonical = new Snapshot(1, "test", entries, Counts.of(entries), List.of());
        var display = InventoryDisplay.project(canonical);
        check(display.rows().size() == 6 && display.counts().userMods() == 5, "five real mods plus one API summary");
        check(canonical.entries().size() == 51 && canonical.counts().bundledApi() == 46, "logical API records never deleted");
        check(display.apiCredits().size() == 46 && display.apiCredits().getFirst().licenses().equals(List.of("Apache-2.0")), "credits retain original metadata/licenses");
        List<String> types = display.rows().stream().map(InventoryDisplay.Row::compatibilityType).toList();
        check(types.equals(List.of("NeoForge 兼容", "Forge 兼容", "Fabric 兼容", "Fabric 兼容", "Quilt 兼容", "U ∞ I 内置")), "compatibility detail follows admitted lanes");
        check(display.rows().getLast() instanceof InventoryDisplay.ApiSummaryRow && display.rows().getLast().displayName().equals("Unified ∞ Infinity API"), "explicit non-container summary");
        check(display.counts().visibleRealRows() + display.counts().collapsedApiModules() == canonical.entries().size(), "display count reconciliation");
        Entry userApi = displayEntry("my_api", "My API", Ecosystem.FABRIC, Lane.FABRIC_PROJECTION, Category.USER_MOD, Evidence.ORIGINAL_INTAKE);
        Entry forgedApi = displayEntry("forged", "Internal API", Ecosystem.NEOFORGE, Lane.NATIVE_HOST, Category.BUNDLED_API, Evidence.ORIGINAL_INTAKE);
        Entry unknown = displayEntry("unknown", "Unknown", Ecosystem.UNKNOWN, Lane.UNKNOWN, Category.UNKNOWN, Evidence.UNKNOWN);
        Snapshot extras = new Snapshot(1, "test", List.of(userApi, forgedApi, unknown), Counts.of(List.of(userApi, forgedApi, unknown)), List.of());
        var extraDisplay = InventoryDisplay.project(extras);
        check(extraDisplay.rows().size() == 3 && extraDisplay.apiCredits().isEmpty(), "API name or untrusted category cannot hide ordinary rows");
        check(extraDisplay.rows().getLast().compatibilityType().equals("未知"), "unknown lane explicitly unknown");
        Entry game = displayEntry("minecraft", "Minecraft", Ecosystem.UNKNOWN, Lane.GAME, Category.PLATFORM, Evidence.SELECTED_HOST);
        check(InventoryDisplay.compatibilityType(game).equals("Minecraft 内置"), "verified game lane uses game label");
        check(display.rows().stream().noneMatch(r -> r.compatibilityType().equals(InventoryDisplay.UNIFIED_NATIVE_LABEL)), "no hosted mod claims independent Unified native route");
        var filtered = InventoryDisplay.filter(display, "", "farmersdelight");
        check(filtered.rows().size() == 1 && filtered.resetScrollToTop() && filtered.clearSelection(), "filter change resets offscreen scroll/selection");
        check(!InventoryDisplay.filter(display, "farmersdelight", "farmersdelight").resetScrollToTop(), "unchanged query does not jitter scroll");
        expect(UnsupportedOperationException.class, () -> display.apiCredits().clear());
    }
    private static Entry displayEntry(String id, String name, Ecosystem ecosystem, Lane lane, Category category, Evidence evidence) {
        return new Entry(id, Optional.of(id), name, Optional.of("1.0+raw"), Optional.of("1.0+raw"), "1.0_raw",
            ecosystem, lane, category, Optional.empty(), List.of("Apache-2.0"),
            new Provenance(List.of(new SourceChain("/original.jar", List.of())), "/runtime.jar", Optional.empty(), evidence));
    }
    private static Candidate candidate(Path root, Ecosystem ecosystem, String... ids) {
        Path path = root.resolve(String.join("-", ids) + ".jar");
        return new Candidate(path, new SourceChain(path.toString(), List.of()), ecosystem, List.of(ids), false);
    }
    private static Entry entry(String id, String name, String version, Category category) {
        return new Entry(id, Optional.of(id), name, Optional.of(version), Optional.of(version), version.replace('+', '_'),
            Ecosystem.FABRIC, Lane.FABRIC_PROJECTION, category, Optional.empty(),
            new Provenance(List.of(new SourceChain("/original.jar", List.of())), "/runtime.jar", Optional.empty(), Evidence.ORIGINAL_INTAKE));
    }
    private static String hash(Path path) throws Exception { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path))); }
    private static void check(boolean condition, String message) { checks++; if (!condition) throw new AssertionError(message); }
    private static void expect(Class<? extends Throwable> type, Checked action) {
        checks++; try { action.run(); } catch (Throwable error) { if (type.isInstance(error)) return; throw new AssertionError(error); }
        throw new AssertionError("Expected " + type.getSimpleName());
    }
    @FunctionalInterface private interface Checked { void run() throws Exception; }
}
