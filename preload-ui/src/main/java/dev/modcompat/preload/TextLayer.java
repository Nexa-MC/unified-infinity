package dev.modcompat.preload;

import java.awt.Color;
import java.awt.Font;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;

/** Own typography/layout, rasterized only when text or viewport geometry changes; no external font or image assets. */
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
        return render(state, reducedMotion, ResponsiveLayout.of(WIDTH, HEIGHT, WIDTH, HEIGHT));
    }
    static BufferedImage render(ProgressSnapshot state, boolean reducedMotion, ResponsiveLayout layout) {
        BufferedImage image = new BufferedImage(layout.pixelWidth(), layout.pixelHeight(), BufferedImage.TYPE_INT_ARGB);
        paint(image, state, reducedMotion, layout);
        return image;
    }
    /** Reuses pixel storage during continuous resize; only small raster/image wrappers change shape. */
    static final class Canvas {
        private final int[] pixels = new int[(int) ResponsiveLayout.MAX_TEXTURE_PIXELS];
        private BufferedImage image;
        BufferedImage render(ProgressSnapshot state, boolean reducedMotion, ResponsiveLayout layout) {
            if (image == null || image.getWidth() != layout.pixelWidth() || image.getHeight() != layout.pixelHeight()) {
                var buffer = new java.awt.image.DataBufferInt(pixels, pixels.length);
                var raster = java.awt.image.Raster.createPackedRaster(buffer, layout.pixelWidth(), layout.pixelHeight(), layout.pixelWidth(),
                        new int[] {0xff0000, 0xff00, 0xff, 0xff000000}, null);
                image = new BufferedImage(java.awt.image.ColorModel.getRGBdefault(), raster, false, null);
            }
            java.util.Arrays.fill(pixels, 0, layout.pixelWidth() * layout.pixelHeight(), 0);
            paint(image, state, reducedMotion, layout);
            return image;
        }
    }
    private static void paint(BufferedImage image, ProgressSnapshot state, boolean reducedMotion, ResponsiveLayout layout) {
        Graphics2D g = image.createGraphics();
        try {
            g.scale(layout.pixelWidth() / layout.width(), layout.pixelHeight() / layout.height());
            g.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_ON);
            g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
            g.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BILINEAR);
            g.setFont(new Font(Font.SANS_SERIF, Font.PLAIN, 13));
            g.setColor(new Color(127, 144, 166));
            g.drawString("U N I F I E D", (float) layout.margin(), (float) (layout.headerLine() - 19));
            String mode = reducedMotion ? "REDUCED MOTION" : "Minecraft 1.21.1 · Java 21";
            g.drawString("COMPATIBILITY RUNTIME", (float) layout.margin(), (float) (layout.height() - (layout.stackedFooter() ? 49 : 28)));
            float modeX = (float) (layout.stackedFooter() ? layout.margin()
                    : layout.width() - layout.margin() - g.getFontMetrics().stringWidth(mode));
            g.drawString(mode, modeX, (float) (layout.height() - 28));
            g.drawImage(ICON, (int) layout.iconX(), (int) layout.iconTop(), (int) layout.iconSize(), (int) layout.iconSize(), null);
            g.setFont(new Font(Font.SANS_SERIF, Font.BOLD, layout.compact() ? 23 : 31));
            fitFont(g, "Unified ∞ Infinity", layout.contentWidth(), 20);
            g.setColor(new Color(237, 243, 250));
            centered(g, "Unified ∞ Infinity", layout.titleBaseline(), layout.width());
            g.setFont(new Font(Font.SANS_SERIF, Font.PLAIN, layout.compact() ? 14 : 18));
            fitFont(g, state.heading(), layout.contentWidth(), 13);
            g.setColor(new Color(200, 212, 228));
            centered(g, state.heading(), layout.stageBaseline(), layout.width());
            g.setFont(new Font(Font.SANS_SERIF, Font.PLAIN, 13));
            g.setColor(state.status().equals("failed") ? new Color(255, 134, 126) : new Color(137, 155, 178));
            java.util.List<String> lines = wrap(g, state.detail(), layout.contentWidth(), 2);
            for (int i = 0; i < lines.size(); i++) centered(g, lines.get(i), layout.detailBaseline() + i * 16, layout.width());
        } finally { g.dispose(); }
    }
    private static void fitFont(Graphics2D g, String text, double available, int minimum) {
        while (g.getFont().getSize() > minimum && g.getFontMetrics().stringWidth(text) > available)
            g.setFont(g.getFont().deriveFont((float) g.getFont().getSize() - 1));
    }
    static java.util.List<String> wrap(Graphics2D g, String text, double width, int maxLines) {
        java.util.List<String> lines = new java.util.ArrayList<>();
        String rest = text;
        while (!rest.isEmpty() && lines.size() < maxLines) {
            if (g.getFontMetrics().stringWidth(rest) <= width) { lines.add(rest); break; }
            int end = rest.length();
            boolean last = lines.size() == maxLines - 1;
            String suffix = last ? "…" : "";
            while (end > 1 && g.getFontMetrics().stringWidth(rest.substring(0, end) + suffix) > width) end--;
            if (!last) {
                int space = rest.lastIndexOf(' ', end);
                if (space > 0) end = space;
            }
            lines.add(rest.substring(0, end).stripTrailing() + suffix);
            rest = last ? "" : rest.substring(end).stripLeading();
        }
        return lines;
    }
    private static void centered(Graphics2D g, String text, double y, double width) {
        g.drawString(text, (float) ((width - g.getFontMetrics().stringWidth(text)) / 2), (float) y);
    }
}
