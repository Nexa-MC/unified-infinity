package dev.modcompat.runtime.branding;

public final class BrandingTextTests {
    private static int count;
    private static void same(String expected, String actual) {
        if (!java.util.Objects.equals(expected, actual)) throw new AssertionError(expected + " != " + actual);
        count++;
    }
    public static void main(String[] args) {
        same("Unified ∞ Infinity (49 mods)", BrandingText.titleScreenLine("NeoForge 21.1.219 (49 mods)"));
        same("Unified ∞ Infinity (49个模组)", BrandingText.titleScreenLine("NeoForge 21.1.219 (49个模组)"));
        same("Minecraft 1.21.1", BrandingText.titleScreenLine("Minecraft 1.21.1"));
        same("Copyright Mojang AB. Do not distribute!", BrandingText.titleScreenLine("Copyright Mojang AB. Do not distribute!"));
        same("Some other mod", BrandingText.titleScreenLine("Some other mod"));
        same("Unified ∞ Infinity", BrandingText.titleScreenLine("NeoForge 21.1.219"));
        same("Unified ∞ Infinity | Minecraft 1.21.1", BrandingText.windowTitle("Minecraft NeoForge* 1.21.1"));
        same("Unified ∞ Infinity | Minecraft 1.21.1 - Singleplayer", BrandingText.windowTitle("Minecraft NeoForge* 1.21.1 - Singleplayer"));
        same("Unified ∞ Infinity | Minecraft 1.21.1", BrandingText.windowTitle("Unified ∞ Infinity | Minecraft 1.21.1"));
        same(null, BrandingText.windowTitle(null));
        System.out.println("PASS: " + count + " client branding text contracts");
    }
}
