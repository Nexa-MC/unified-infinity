package dev.modcompat.runtime.branding;

/** Narrow presentation rules; upstream identities and protocol branding are untouched. */
public final class BrandingText {
    public static final String NAME = "Unified ∞ Infinity";
    private BrandingText() { }
    public static String titleScreenLine(String original) {
        if (original == null || !original.startsWith("NeoForge ")) return original;
        // Keep the original localized mod-count suffix, replacing only the host name/version token.
        int suffix = original.indexOf(' ', "NeoForge ".length());
        return NAME + (suffix < 0 ? "" : original.substring(suffix));
    }
    public static String windowTitle(String original) {
        if (original == null || original.startsWith(NAME)) return original;
        // Preserve Minecraft version and any later singleplayer/server context in the title.
        String minecraftTitle = original.replace("Minecraft NeoForge*", "Minecraft").replace("Minecraft NeoForge", "Minecraft");
        return NAME + " | " + minecraftTitle;
    }
}
