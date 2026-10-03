package org.sinytra.connector.infinity.inventory;

import java.util.*;
import static org.sinytra.connector.infinity.inventory.AdmissionInventory.*;

/** Presentation-only projection. Summary rows are not ModContainers, mod IDs or dependency providers. */
public final class InventoryDisplay {
    public static final String API_SUMMARY_NAME = "Unified ∞ Infinity API";
    /** Reserved wording only; no independent Unified admission route is implemented. */
    public static final String UNIFIED_NATIVE_LABEL = "U ∞ I 原生";
    public static final String COMPATIBILITY_FIELD = "兼容类型";
    private InventoryDisplay() {}

    public sealed interface Row permits ModRow, ApiSummaryRow {
        String displayName();
        String compatibilityType();
    }
    public record ModRow(Entry entry) implements Row {
        public ModRow { Objects.requireNonNull(entry); }
        @Override public String displayName() { return entry.displayName(); }
        @Override public String compatibilityType() { return InventoryDisplay.compatibilityType(entry); }
    }
    /** Explicitly has no canonicalId(), loadedVersion() or container. */
    public record ApiSummaryRow(int logicalModuleCount) implements Row {
        public ApiSummaryRow { if (logicalModuleCount < 1) throw new IllegalArgumentException("Empty API summary"); }
        @Override public String displayName() { return API_SUMMARY_NAME; }
        @Override public String compatibilityType() { return "U ∞ I 内置"; }
    }
    public record DisplayCounts(int loadedLogicalMods, int visibleRealRows, int collapsedApiModules,
                                int apiSummaryRows, int visibleRows, int userMods) {
        public DisplayCounts {
            if (loadedLogicalMods != visibleRealRows + collapsedApiModules
                || visibleRows != visibleRealRows + apiSummaryRows
                || apiSummaryRows != (collapsedApiModules == 0 ? 0 : 1))
                throw new IllegalArgumentException("Display counts must reconcile to authoritative logical entries");
        }
    }
    /** apiCredits retain the exact hidden entry identities, versions, provenance and license expressions. */
    public record Projection(List<Row> rows, List<Entry> apiCredits, DisplayCounts counts) {
        public Projection {
            rows = List.copyOf(rows); apiCredits = List.copyOf(apiCredits); Objects.requireNonNull(counts);
            if (rows.size() != counts.visibleRows() || apiCredits.size() != counts.collapsedApiModules())
                throw new IllegalArgumentException("Projection collections do not match counts");
        }
    }
    public static Projection project(Snapshot authoritative) {
        List<Entry> credits = authoritative.entries().stream().filter(InventoryDisplay::isTrustedBundledApi).toList();
        List<Row> rows = new ArrayList<>(); boolean summarized = false;
        for (Entry entry : authoritative.entries()) {
            if (isTrustedBundledApi(entry)) {
                if (!summarized) { rows.add(new ApiSummaryRow(credits.size())); summarized = true; }
            } else rows.add(new ModRow(entry));
        }
        int realRows = authoritative.entries().size() - credits.size();
        return new Projection(rows, credits, new DisplayCounts(authoritative.entries().size(), realRows,
            credits.size(), summarized ? 1 : 0, rows.size(), authoritative.counts().userMods()));
    }
    /** UI adapter must apply these reset signals before displaying a changed filtered list. */
    public record FilterResult(List<Row> rows, boolean resetScrollToTop, boolean clearSelection) {
        public FilterResult { rows = List.copyOf(rows); }
    }
    public static FilterResult filter(Projection projection, String previousQuery, String query) {
        Objects.requireNonNull(query);
        String normalized = query.toLowerCase(Locale.ROOT);
        List<Row> visible = projection.rows().stream().filter(row -> row instanceof ModRow mod
            ? mod.entry().matches(query) : row.displayName().toLowerCase(Locale.ROOT).contains(normalized)).toList();
        boolean changed = !Objects.equals(previousQuery, query);
        return new FilterResult(visible, changed, changed);
    }
    public static String compatibilityType(Entry entry) {
        if (entry.lane() == Lane.GAME) return "Minecraft 内置";
        if ((entry.category() == Category.BUNDLED_API || entry.category() == Category.PLATFORM)
            && entry.provenance().evidence() == Evidence.MANAGED_PINNED_EXTRACTION) return "U ∞ I 内置";
        return switch (entry.lane()) {
            case GAME -> "Minecraft 内置";
            case NATIVE_HOST -> "NeoForge 兼容";
            case FORGE_ADAPTER -> "Forge 兼容";
            case FABRIC_PROJECTION -> "Fabric 兼容";
            case NATIVE_QUILT -> "Quilt 兼容";
            case UNKNOWN -> "未知";
        };
    }
    private static boolean isTrustedBundledApi(Entry entry) {
        return entry.category() == Category.BUNDLED_API
            && entry.provenance().evidence() == Evidence.MANAGED_PINNED_EXTRACTION;
    }
}
