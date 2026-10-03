package dev.modcompat.preload;

import java.awt.Color;
import java.awt.Font;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;

/** Own typography/layout, rasterized only when its text changes; no external font or image assets. */
public final class TextLayer {
    public static final int WIDTH = 960, HEIGHT = 540;
    private static final BufferedImage ICON = loadIcon();
    private TextLayer() { }
    private static BufferedImage loadIcon() {
        try (var stream = TextLayer.class.getResourceAsStream("/infinity-icon.png")) {
            if (stream == null) throw new IllegalStateException("Bundled Infinity icon is missing");
            return javax.imageio.ImageIO.read(stream);
        } catch (java.io.IOException e) { throw new IllegalStateException("Unable to load own icon", e); }
    }
    static BufferedImage icon() { return ICON; }
    public static BufferedImage render(ProgressSnapshot state, boolean reducedMotion) {
        BufferedImage image = new BufferedImage(WIDTH, HEIGHT, BufferedImage.TYPE_INT_ARGB);
        Graphics2D g = image.createGraphics();
        try {
            g.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_ON);
            g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
            g.setFont(new Font(Font.SANS_SERIF, Font.PLAIN, 13));
            g.setColor(new Color(127, 144, 166));
            g.drawString("U N I F I E D", 42, 39);
            g.drawString("COMPATIBILITY RUNTIME", 42, HEIGHT - 28);
            String mode = reducedMotion ? "REDUCED MOTION" : "Minecraft 1.21.1 · Java 21";
            g.drawString(mode, WIDTH - 42 - g.getFontMetrics().stringWidth(mode), HEIGHT - 28);
            g.drawImage(ICON, 376, 78, 208, 208, null);
            g.setFont(new Font(Font.SANS_SERIF, Font.BOLD, 31));
            g.setColor(new Color(237, 243, 250));
            centered(g, "Unified ∞ Infinity", 312);
            g.setFont(new Font(Font.SANS_SERIF, Font.PLAIN, 18));
            g.setColor(new Color(200, 212, 228));
            centered(g, state.heading(), 371);
            g.setFont(new Font(Font.SANS_SERIF, Font.PLAIN, 13));
            g.setColor(state.status().equals("failed") ? new Color(255, 134, 126) : new Color(137, 155, 178));
            centered(g, state.detail(), 430);
        } finally { g.dispose(); }
        return image;
    }
    private static void centered(Graphics2D g, String text, int y) {
        g.drawString(text, (WIDTH - g.getFontMetrics().stringWidth(text)) / 2, y);
    }
}
