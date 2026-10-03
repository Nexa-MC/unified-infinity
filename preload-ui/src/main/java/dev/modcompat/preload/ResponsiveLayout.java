package dev.modcompat.preload;

/** Native-free geometry. Window units set UI size; framebuffer pixels set raster density. */
final record ResponsiveLayout(double width, double height, int pixelWidth, int pixelHeight,
        double margin, double headerLine, double footerLine, double iconTop, double iconSize,
        double titleBaseline, double stageBaseline, double barY, double detailBaseline,
        double barWidth, boolean compact, boolean stackedFooter) {
    static final int MAX_TEXTURE_EDGE = 2048;
    static final long MAX_TEXTURE_PIXELS = 2_097_152;

    static boolean drawable(int windowWidth, int windowHeight, int framebufferWidth, int framebufferHeight) {
        return windowWidth > 0 && windowHeight > 0 && framebufferWidth > 0 && framebufferHeight > 0;
    }

    static ResponsiveLayout of(int windowWidth, int windowHeight, int framebufferWidth, int framebufferHeight) {
        if (!drawable(windowWidth, windowHeight, framebufferWidth, framebufferHeight))
            throw new IllegalArgumentException("A minimized/zero-sized surface has no layout");
        // A tiny compositor surface still gets finite geometry; below 320x320 readability is physically limited.
        // Use one scale for both axes. Independent X/Y scaling would distort the supplied square icon and text.
        double uiScale = Math.min(1, Math.min(windowWidth / 320.0, windowHeight / 320.0));
        double w = windowWidth / uiScale, h = windowHeight / uiScale;
        double density = Math.min(1, Math.min((double) MAX_TEXTURE_EDGE / framebufferWidth,
                (double) MAX_TEXTURE_EDGE / framebufferHeight));
        density = Math.min(density, Math.sqrt((double) MAX_TEXTURE_PIXELS / ((double) framebufferWidth * framebufferHeight)));
        int pw = Math.max(1, (int) Math.floor(framebufferWidth * density));
        int ph = Math.max(1, (int) Math.floor(framebufferHeight * density));
        boolean compact = h < 440, stacked = w < 620;
        double margin = Math.min(42, Math.max(16, w * .044));
        double header = compact ? 46 : 58, footer = h - (stacked ? 76 : 54);
        double titleGap = compact ? 28 : 36, stageGap = compact ? 28 : 40;
        double barGap = compact ? 18 : 22, detailGap = compact ? 24 : 32;
        double overhead = titleGap + stageGap + barGap + detailGap + 22;
        double available = footer - header - 24;
        double icon = Math.max(16, Math.min(208, Math.min((w - 2 * margin) * .65, available - overhead)));
        double top = header + 12 + Math.max(0, (available - icon - overhead) / 2);
        double title = top + icon + titleGap, stage = title + stageGap, bar = stage + barGap;
        return new ResponsiveLayout(w, h, pw, ph, margin, header, footer, top, icon,
                title, stage, bar, bar + detailGap, Math.min(420, w - 2 * margin), compact, stacked);
    }

    double centerX() { return width / 2; }
    double iconX() { return centerX() - iconSize / 2; }
    double barX() { return centerX() - barWidth / 2; }
    double contentWidth() { return width - 2 * margin; }
}
