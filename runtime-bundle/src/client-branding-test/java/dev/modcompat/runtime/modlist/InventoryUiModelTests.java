package dev.modcompat.runtime.modlist;

import java.util.*;
import org.sinytra.connector.infinity.inventory.AdmissionInventory.*;
import org.sinytra.connector.infinity.inventory.InventoryDisplay;
import org.sinytra.connector.infinity.inventory.InventoryDisplay.*;

/** Headless Java 21 contracts. No Minecraft, OpenGL, discovery, services or mod entrypoints. */
public final class InventoryUiModelTests {
    private static int checks;
    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message); checks++;
    }
    private static Entry entry(String id, String name, Lane lane, Category category, Evidence evidence) {
        return new Entry(id, Optional.of(id), name, Optional.of("1.0+original"), Optional.of("1.0+original"), "1.0_effective",
            Ecosystem.UNKNOWN, lane, category, Optional.empty(), List.of("MIT"), new Provenance(
                List.of(new SourceChain("mods/renamed.jar", List.of("META-INF/jars/module.jar"))), "cache/transformed.jar",
                Optional.of("a".repeat(64)), evidence));
    }
    public static void main(String[] args) {
        List<Entry> entries = new ArrayList<>();
        entries.add(entry("farmersdelight", "Farmer's Delight", Lane.NATIVE_HOST, Category.USER_MOD, Evidence.ORIGINAL_INTAKE));
        entries.add(entry("clumps", "Clumps", Lane.FORGE_ADAPTER, Category.USER_MOD, Evidence.ORIGINAL_INTAKE));
        entries.add(entry("lithium", "Lithium", Lane.FABRIC_PROJECTION, Category.USER_MOD, Evidence.ORIGINAL_INTAKE));
        entries.add(entry("chunky", "Chunky", Lane.FABRIC_PROJECTION, Category.USER_MOD, Evidence.ORIGINAL_INTAKE));
        entries.add(entry("optab", "Op Tab", Lane.NATIVE_QUILT, Category.USER_MOD, Evidence.ORIGINAL_INTAKE));
        entries.add(entry("minecraft", "Minecraft", Lane.GAME, Category.PLATFORM, Evidence.SELECTED_HOST));
        entries.add(entry("fabric_api", "Fabric API", Lane.NATIVE_HOST, Category.BUNDLED_API, Evidence.MANAGED_PINNED_EXTRACTION));
        entries.add(entry("quilt_base", "Quilt Base", Lane.NATIVE_QUILT, Category.BUNDLED_API, Evidence.MANAGED_PINNED_EXTRACTION));
        entries.add(entry("user_api", "My API", Lane.NATIVE_HOST, Category.USER_MOD, Evidence.ORIGINAL_INTAKE));
        entries.add(entry("unverified_api", "Unverified API", Lane.NATIVE_HOST, Category.BUNDLED_API, Evidence.UNKNOWN));
        Snapshot snapshot = new Snapshot(1, "test", entries, Counts.of(entries), List.of());
        InventoryUiModel ui = new InventoryUiModel(snapshot);
        require(ui.rows().size() == 9, "Only trusted bundled API entries collapse");
        require(ui.projection().apiCredits().size() == 2, "All trusted upstream credits survive");
        require(ui.projection().counts().loadedLogicalMods() == 10, "Logical count remains authoritative");
        require(snapshot.entries().size() == 10, "No registry/snapshot mutation");
        require(ui.rows().stream().filter(ApiSummaryRow.class::isInstance).count() == 1, "One display aggregate");
        require(ui.rows().stream().anyMatch(r -> r.displayName().equals("Unified ∞ Infinity API")), "Exact API summary name");
        require(ui.rows().stream().anyMatch(r -> r.displayName().equals("My API")), "User API name stays visible");
        require(ui.rows().stream().anyMatch(r -> r.displayName().equals("Unverified API")), "No evidence-free hiding");
        String[] labels = {"NeoForge 兼容", "Forge 兼容", "Fabric 兼容", "Fabric 兼容", "Quilt 兼容", "Minecraft 内置"};
        for (int i = 0; i < labels.length; i++) require(InventoryDisplay.compatibilityType(entries.get(i)).equals(labels[i]), "Exact real-mod/game label " + i);
        require(InventoryDisplay.compatibilityType(entries.get(6)).equals("U ∞ I 内置"), "Trusted built-in label");
        require(InventoryDisplay.UNIFIED_NATIVE_LABEL.equals("U ∞ I 原生"), "Exact reserved native label");
        require(ui.rows().stream().noneMatch(r -> r.compatibilityType().equals("U ∞ I 原生")), "No false native mod claims");
        ui.select(ui.rows().get(0));
        require(ui.query(" FARMERSDELIGHT "), "Name-independent canonical ID query changes viewport");
        require(ui.rows().size() == 1 && ui.rows().get(0).displayName().equals("Farmer's Delight"), "ID query finds Farmer's Delight");
        require(ui.selected() == null, "Query clears stale selection/config target");
        require(!ui.query("FARMERSDELIGHT"), "Identical normalized query does not reset every tick");
        require(ui.query("optab") && ui.rows().size() == 1 && ui.rows().get(0).displayName().equals("Op Tab"), "Op Tab ID query");
        require(ui.query("  ") && ui.rows().size() == 9, "Clearing query restores projected rows");
        ui.select(ui.rows().get(4)); Object selected = ui.selected();
        ui.nextSort(); require(ui.selected() == selected, "Sort retains selected logical row");
        require(ui.rows().get(0).displayName().equals("Chunky"), "Name ascending sort");
        ui.nextSort(); require(ui.rows().get(0).displayName().equals("Unverified API"), "Name descending sort");
        ui.nextSort(); require(ui.rows().get(0).displayName().equals("Farmer's Delight"), "Loaded order restores snapshot order");
        require(ui.query("missing") && ui.rows().isEmpty() && ui.selected() == null, "Empty search clears selection");
        ui.select(new ApiSummaryRow(7)); require(ui.selected() == null, "Cannot select a detached aggregate");
        ui.query("x".repeat(1000)); require(ui.query().length() <= InventoryUiModel.MAX_QUERY, "Query bounded");
        require(InventoryUiModel.version(entries.get(2)).equals("1.0+original"), "Original version preserved");
        require(InventoryUiModel.source(entries.get(2).provenance().installationSources().getFirst()).equals("mods/renamed.jar!/META-INF/jars/module.jar"), "Archive path distinguished from runtime");
        require(InventoryUiModel.plain("§cA\u0000\u202eB\nC\tD", 100).equals("AB\nC D"), "Control/style/bidi stripping");
        require(InventoryUiModel.plain(null, 100).isEmpty(), "Null presentation text safe");
        require(InventoryUiModel.plain("😀😀😀", 2).equals("😀😀…"), "Code-point-safe bounded strings");
        for (int width : new int[]{320, 440, 640, 854, 1920}) for (int height : new int[]{180, 240, 480, 1080}) {
            var l = InventoryUiModel.Layout.of(width, height);
            for (var rect : List.of(l.search(), l.sort(), l.list(), l.details())) {
                require(rect.width() > 0 && rect.height() > 0, "Positive panel dimensions");
                require(rect.x() >= 0 && rect.x() + rect.width() <= width, "Panels fit horizontal viewport");
                require(rect.y() >= 0 && rect.y() + rect.height() < l.footerY(), "Panels do not overlap footer");
            }
            require(l.footerY() + 20 <= height, "Footer fits viewport");
            require(l.list().x() + l.list().width() <= l.details().x() || l.list().y() + l.list().height() <= l.details().y(), "List/detail do not overlap");
        }
        try { ui.rows().add(new ApiSummaryRow(1)); throw new AssertionError("Mutable rows"); } catch (UnsupportedOperationException expected) { checks++; }
        System.out.println("PASS: " + checks + " inventory UI model/layout contracts");
    }
}
