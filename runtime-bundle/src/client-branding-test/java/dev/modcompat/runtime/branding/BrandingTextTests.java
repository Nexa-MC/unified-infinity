package dev.modcompat.runtime.branding;

import org.sinytra.connector.infinity.inventory.AdmissionInventory.Counts;

public final class BrandingTextTests {
    private static int count;
    private static final BrandingText.CountText EN = user -> user + " user mods";
    private static final BrandingText.CountText ZH = user -> user + " 个用户模组";
    private static void same(String expected, String actual) {
        if (!java.util.Objects.equals(expected, actual)) throw new AssertionError(expected + " != " + actual);
        count++;
    }
    public static void main(String[] args) throws Exception {
        Counts actual = new Counts(5, 46, 5, 0);
        same("Unified ∞ Infinity (5 user mods)", BrandingText.titleScreenLine("NeoForge 21.1.219 (56 mods)", actual, EN));
        same("Unified ∞ Infinity (5 个用户模组)", BrandingText.titleScreenLine("NeoForge 21.1.219 (56个模组)", actual, ZH));
        same("Unified ∞ Infinity (5 user mods)", BrandingText.titleScreenLine("NeoForge 21.1.219 (999 stale mods)", actual, EN));
        same("Unified ∞ Infinity (5 user mods)", BrandingText.titleScreenLine("NeoForge 21.1.219", actual, EN));
        same("Unified ∞ Infinity", BrandingText.titleScreenLine("NeoForge 21.1.219 (56 mods)"));
        same("Unified ∞ Infinity", BrandingText.titleScreenLine("NeoForge 21.1.219 (56个模组)"));
        same("Unified ∞ Infinity", BrandingText.titleScreenLine("NeoForge 21.1.219", null, EN));
        same("Unified ∞ Infinity", BrandingText.titleScreenLine("NeoForge 21.1.219", actual, null));
        Counts unknown = new Counts(5, 44, 5, 2);
        same("Unified ∞ Infinity (5 user mods)", BrandingText.titleScreenLine("NeoForge 21.1.219", unknown, EN));
        same("Unified ∞ Infinity (5 个用户模组)", BrandingText.titleScreenLine("NeoForge 21.1.219", unknown, ZH));
        same("Unified ∞ Infinity (0 user mods)", BrandingText.titleScreenLine("NeoForge 21.1.219", new Counts(0, 0, 0, 3), EN));
        same("Unified ∞ Infinity (0 user mods)", BrandingText.titleScreenLine("NeoForge 21.1.219", new Counts(0, 0, 0, 0), EN));
        same("Unified ∞ Infinity", BrandingText.titleScreenLine("NeoForge 21.1.219", new Counts(-1, 0, 0, 0), EN));
        same("Unified ∞ Infinity", BrandingText.titleScreenLine("NeoForge 21.1.219", new Counts(Integer.MAX_VALUE, 1, 0, 0), EN));
        same("Unified ∞ Infinity", BrandingText.titleScreenLine("NeoForge 21.1.219", actual, u -> ""));
        same("Unified ∞ Infinity", BrandingText.titleScreenLine("NeoForge 21.1.219", actual, u -> null));
        same(null, BrandingText.titleScreenLine(null, actual, EN));
        same("Minecraft 1.21.1", BrandingText.titleScreenLine("Minecraft 1.21.1", actual, EN));
        same("Copyright Mojang AB. Do not distribute!", BrandingText.titleScreenLine("Copyright Mojang AB. Do not distribute!", actual, ZH));
        same("Some other mod", BrandingText.titleScreenLine("Some other mod", actual, EN));
        same("Unified ∞ Infinity", BrandingText.titleScreenLine("Unified ∞ Infinity", actual, EN));
        same("Unified ∞ Infinity | Minecraft 1.21.1", BrandingText.windowTitle("Minecraft NeoForge* 1.21.1"));
        same("Unified ∞ Infinity | Minecraft 1.21.1 - Singleplayer", BrandingText.windowTitle("Minecraft NeoForge* 1.21.1 - Singleplayer"));
        same("Unified ∞ Infinity | Minecraft 1.21.1", BrandingText.windowTitle("Unified ∞ Infinity | Minecraft 1.21.1"));
        same(null, BrandingText.windowTitle(null));
        java.util.Properties metrics = new java.util.Properties();
        java.nio.file.Path metricsFile = java.nio.file.Path.of(args.length == 0
            ? "runtime-bundle/src/client-branding-test/resources/default-font-advances.properties" : args[0]);
        try (var reader = java.nio.file.Files.newBufferedReader(metricsFile)) { metrics.load(reader); }
        java.util.function.ToIntFunction<String> measure = text -> text.codePoints().map(cp ->
            Integer.parseInt(metrics.getProperty(Integer.toHexString(cp).toUpperCase(java.util.Locale.ROOT), "9"))).sum();
        same("196", "" + measure.applyAsInt("Copyright Mojang AB. Do not distribute!"));
        same("158", "" + measure.applyAsInt("Unified ∞ Infinity (5 user mods)"));
        same("100", "" + measure.applyAsInt("U ∞ I (5 user mods)"));
        int real1180Budget = (int) Math.ceil(1180.0 / 3) - 196 - 10;
        same("Unified ∞ Infinity (5 user mods)", BrandingText.titleScreenLine("NeoForge 21.1.219 (56 mods)", actual, EN, real1180Budget, measure));
        same("U ∞ I (5 user mods)", BrandingText.titleScreenLine("NeoForge 21.1.219", actual, EN, 320 - 196 - 10, measure));
        same("", BrandingText.titleScreenLine("NeoForge 21.1.219", actual, EN, 0, measure));
        for (int width = 0; width <= 640; width++) {
            for (BrandingText.CountText language : new BrandingText.CountText[]{EN, ZH}) {
                String fitted = BrandingText.titleScreenLine("NeoForge 21.1.219", actual, language, width, measure);
                if (measure.applyAsInt(fitted) > width) throw new AssertionError("Measured footer overflow at " + width);
                count++;
            }
        }
        for (int guiWidth : new int[]{320, 360, 394, 480, 640}) {
            int budget = Math.max(0, guiWidth - 196 - 10);
            String fitted = BrandingText.titleScreenLine("NeoForge 21.1.219", actual, EN, budget, measure);
            if (2 + measure.applyAsInt(fitted) + 6 > guiWidth - 196 - 2) throw new AssertionError("Copyright overlap");
            count++;
        }
        same("U ∞ I", BrandingText.titleScreenLine("NeoForge 21.1.219", null, EN, 35, measure));
        same("Minecraft 1.21.1", BrandingText.titleScreenLine("Minecraft 1.21.1", actual, EN, 0, measure));
        System.out.println("PASS: " + count + " client branding text contracts");
    }
}
