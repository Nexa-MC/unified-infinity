package dev.modcompat.runtime.branding;

import java.util.function.ToIntFunction;
import org.sinytra.connector.infinity.inventory.AdmissionInventory.Counts;

/** Narrow presentation rules; upstream identities and protocol branding are untouched. */
public final class BrandingText {
    public static final String NAME = "Unified ∞ Infinity";
    public static final String COMPACT_NAME = "U ∞ I";
    @FunctionalInterface
    public interface CountText {
        String format(int userMods);
    }
    private BrandingText() { }

    /** With no successful final inventory, retain branding but make no count claim. */
    public static String titleScreenLine(String original) {
        return titleScreenLine(original, null, null);
    }

    /** Unconstrained helper for text contracts; the actual title hook always supplies its pixel budget. */
    public static String titleScreenLine(String original, Counts counts, CountText localizedCounts) {
        return titleScreenLine(original, counts, localizedCounts, Integer.MAX_VALUE, String::length);
    }

    /** Fit whole full/compact labels into measured space left of the unchanged copyright widget. */
    public static String titleScreenLine(String original, Counts counts, CountText localizedCounts,
                                          int availableWidth, ToIntFunction<String> measure) {
        if (original == null || !original.startsWith("NeoForge ")) return original;
        String summary = null;
        if (counts != null && localizedCounts != null && counts.userMods() >= 0 && counts.bundledApi() >= 0
                && counts.platform() >= 0 && counts.unknown() >= 0
                && (long) counts.userMods() + counts.bundledApi() + counts.platform() + counts.unknown() <= Integer.MAX_VALUE)
            summary = localizedCounts.format(counts.userMods());
        String suffix = summary == null || summary.isBlank() ? "" : " (" + summary + ")";
        for (String candidate : new String[]{NAME + suffix, COMPACT_NAME + suffix, NAME, COMPACT_NAME})
            if (measure.applyAsInt(candidate) <= Math.max(0, availableWidth)) return candidate;
        return ""; // An exceptionally narrow window keeps copyright intact instead of painting over it.
    }

    public static String windowTitle(String original) {
        if (original == null || original.startsWith(NAME)) return original;
        // Preserve Minecraft version and any later singleplayer/server context in the title.
        String minecraftTitle = original.replace("Minecraft NeoForge*", "Minecraft").replace("Minecraft NeoForge", "Minecraft");
        return NAME + " | " + minecraftTitle;
    }
}
