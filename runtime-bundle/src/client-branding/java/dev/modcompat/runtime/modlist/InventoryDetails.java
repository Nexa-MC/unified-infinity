package dev.modcompat.runtime.modlist;

import java.util.*;
import net.minecraft.network.chat.Component;
import net.neoforged.fml.ModList;
import org.sinytra.connector.infinity.inventory.AdmissionInventory.*;
import org.sinytra.connector.infinity.inventory.InventoryDisplay;
import org.sinytra.connector.infinity.inventory.InventoryDisplay.*;

/** Read-only presentation of final facts, with native host metadata only for descriptive attribution. */
final class InventoryDetails {
    private InventoryDetails() { }
    static Component tr(String key, Object... args) { return Component.translatable("unified_infinity.mods." + key, args); }
    static Component literal(String text) { return Component.literal(InventoryUiModel.plain(text, 16384)); }
    static Component field(String key, String value) { return tr(key, literal(value)); }
    static List<Component> selected(Row row) {
        if (row == null) return List.of(tr("select"));
        List<Component> lines = new ArrayList<>();
        lines.add(literal(row.displayName()));
        lines.add(field("compatibility", row.compatibilityType()));
        if (row instanceof ApiSummaryRow summary) {
            lines.add(tr("api_summary", summary.logicalModuleCount()));
            lines.add(tr("api_credits"));
            return lines;
        }
        Entry entry = ((ModRow) row).entry();
        identity(lines, entry);
        lines.add(field("category", entry.category().name()));
        entry.apiFamily().ifPresent(f -> lines.add(field("api_family", f)));
        provenance(lines, entry);
        hostAttribution(lines, entry);
        licenses(lines, entry);
        return lines;
    }
    static List<Component> credits(InventoryUiModel model) {
        List<Component> lines = new ArrayList<>();
        lines.add(literal("Unified ∞ Infinity"));
        lines.add(tr("credits_intro"));
        lines.add(tr("credits_upstream"));
        // Keep actual loaded runtime/game identities and versions available after simplifying menu branding.
        List<Entry> platform = model.snapshot().entries().stream().filter(entry -> entry.category() == Category.PLATFORM).toList();
        lines.add(tr("runtime_credit_count", platform.size()));
        for (Entry entry : platform) {
            lines.add(literal(entry.displayName()));
            identity(lines, entry);
            licenses(lines, entry);
        }
        lines.add(tr("compatibility_legend"));
        lines.add(literal("NeoForge 兼容 · Forge 兼容 · Fabric 兼容 · Quilt 兼容 · U ∞ I 内置 · Minecraft 内置"));
        lines.add(tr("native_reserved", InventoryDisplay.UNIFIED_NATIVE_LABEL));
        lines.add(tr("api_credit_count", model.projection().apiCredits().size()));
        for (Entry entry : model.projection().apiCredits()) {
            lines.add(literal(entry.displayName()));
            identity(lines, entry);
            entry.apiFamily().ifPresent(f -> lines.add(field("api_family", f)));
            licenses(lines, entry);
            hostAttribution(lines, entry);
            provenance(lines, entry);
        }
        return List.copyOf(lines);
    }
    static List<Component> exclusions(Snapshot snapshot) {
        List<Component> lines = new ArrayList<>();
        lines.add(tr("exclusions_intro", snapshot.exclusions().size()));
        lines.add(tr("exclusions_unchanged"));
        lines.add(tr("exclusions_replacement_caution"));
        for (Exclusion exclusion : snapshot.exclusions()) {
            lines.add(field("excluded_id", exclusion.originalId()));
            lines.add(field("exclusion_reason", exclusion.reason()));
            lines.add(field("exclusion_rule", exclusion.ruleId()));
            lines.add(field("origin", InventoryUiModel.source(exclusion.source())));
            lines.add(tr(exclusion.earlyServiceProvider() ? "exclusion_early_service" : "exclusion_metadata"));
            switch (exclusion.replacement()) {
                case NOT_VERIFIED -> lines.add(tr("replacement_unverified"));
                case NO_API_REPLACEMENT -> lines.add(tr("replacement_none"));
                case SELECTED_PROVIDER_PRESENT -> lines.add(field("replacement_present", String.join(", ", exclusion.selectedReplacementIds())));
            }
        }
        return List.copyOf(lines);
    }

    private static void identity(List<Component> lines, Entry entry) {
        lines.add(field("id", entry.canonicalId()));
        entry.originalId().filter(id -> !id.equals(entry.canonicalId())).ifPresent(id -> lines.add(field("original_id", id)));
        lines.add(field("version", InventoryUiModel.version(entry)));
        entry.sourceVersion().filter(v -> !v.equals(entry.loadedVersion())).ifPresent(v -> lines.add(field("loaded_version", entry.loadedVersion())));
        entry.declaredVersion().filter(v -> !v.equals(InventoryUiModel.version(entry))).ifPresent(v -> lines.add(field("declared_version", v)));
    }
    private static void licenses(List<Component> lines, Entry entry) {
        lines.add(field("license", entry.licenses().isEmpty() ? tr("not_recorded").getString() : String.join("; ", entry.licenses())));
    }
    private static void provenance(List<Component> lines, Entry entry) {
        if (entry.provenance().installationSources().isEmpty()) lines.add(tr("origin_unknown"));
        else for (SourceChain source : entry.provenance().installationSources()) lines.add(field("origin", InventoryUiModel.source(source)));
        lines.add(field("runtime", entry.provenance().runtimeLocation()));
        entry.provenance().originalSha256().ifPresent(digest -> lines.add(field("sha256", digest)));
        lines.add(field("evidence", entry.provenance().evidence().name()));
    }
    private static void hostAttribution(List<Component> lines, Entry entry) {
        ModList.get().getModContainerById(entry.canonicalId()).ifPresent(container -> {
            var info = container.getModInfo();
            for (String key : List.of("authors", "credits", "displayURL")) {
                info.getConfig().<Object>getConfigElement(key).filter(String.class::isInstance).map(String.class::cast)
                    .filter(s -> !s.isBlank()).ifPresent(value -> lines.add(field(key, value)));
            }
            String description = info.getDescription();
            if (description != null && !description.isBlank()) lines.add(literal(description));
        });
    }
}
