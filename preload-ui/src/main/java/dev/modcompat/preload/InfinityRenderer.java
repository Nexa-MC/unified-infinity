package dev.modcompat.preload;

import java.awt.image.BufferedImage;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.FloatBuffer;
import static org.lwjgl.opengl.GL32C.*;

/** Entirely own GL 3.2 scene. No FML visuals, shared static VBOs, default font, or animation. */
final class InfinityRenderer implements AutoCloseable {
    private int width = TextLayer.WIDTH, height = TextLayer.HEIGHT;
    private final int program, vao, vbo, fbo, texture, textTexture, texturedUniform, sizeUniform;
    private final ByteBuffer textPixels = ByteBuffer.allocateDirect((int) ResponsiveLayout.MAX_TEXTURE_PIXELS * 4);
    private final TextLayer.Canvas textCanvas = new TextLayer.Canvas();
    private final FloatBuffer vertices = ByteBuffer.allocateDirect(8192 * 8 * Float.BYTES).order(ByteOrder.nativeOrder()).asFloatBuffer();
    private ProgressSnapshot textState;
    private ResponsiveLayout textLayout;
    private final boolean reducedMotion;
    private final long startNanos = System.nanoTime();
    private boolean closed;

    InfinityRenderer(boolean reducedMotion) {
        this.reducedMotion = reducedMotion;
        String vertex = """
                #version 150
                in vec2 p; in vec2 uv; in vec4 color;
                uniform vec2 sceneSize;
                out vec2 texcoord; out vec4 tint;
                void main() {
                    // FML's overlay contract expects a vertically inverted render texture.
                    gl_Position = vec4(p.x * 2.0 / sceneSize.x - 1.0, p.y * 2.0 / sceneSize.y - 1.0, 0.0, 1.0);
                    texcoord = uv; tint = color;
                }
                """;
        String fragment = """
                #version 150
                in vec2 texcoord; in vec4 tint;
                uniform sampler2D image; uniform int textured;
                out vec4 outputColor;
                void main() { outputColor = tint * (textured == 1 ? texture(image, texcoord) : vec4(1)); }
                """;
        int vs = shader(GL_VERTEX_SHADER, vertex), fs = shader(GL_FRAGMENT_SHADER, fragment);
        program = glCreateProgram();
        glAttachShader(program, vs); glAttachShader(program, fs);
        glBindAttribLocation(program, 0, "p"); glBindAttribLocation(program, 1, "uv"); glBindAttribLocation(program, 2, "color");
        glLinkProgram(program); glDeleteShader(vs); glDeleteShader(fs);
        if (glGetProgrami(program, GL_LINK_STATUS) == GL_FALSE) throw new IllegalStateException("Infinity shader link: " + glGetProgramInfoLog(program));
        texturedUniform = glGetUniformLocation(program, "textured");
        sizeUniform = glGetUniformLocation(program, "sceneSize");
        vao = glGenVertexArrays(); vbo = glGenBuffers();
        glBindVertexArray(vao); glBindBuffer(GL_ARRAY_BUFFER, vbo);
        for (int i = 0; i < 3; i++) glEnableVertexAttribArray(i);
        glVertexAttribPointer(0, 2, GL_FLOAT, false, 32, 0);
        glVertexAttribPointer(1, 2, GL_FLOAT, false, 32, 8);
        glVertexAttribPointer(2, 4, GL_FLOAT, false, 32, 16);
        texture = newTexture();
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, (ByteBuffer) null);
        fbo = glGenFramebuffers(); glBindFramebuffer(GL_FRAMEBUFFER, fbo);
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, texture, 0);
        if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) throw new IllegalStateException("Infinity framebuffer incomplete");
        textTexture = newTexture();
        glBindFramebuffer(GL_FRAMEBUFFER, 0); glBindVertexArray(0);
    }
    private static int shader(int type, String source) {
        int id = glCreateShader(type); glShaderSource(id, source); glCompileShader(id);
        if (glGetShaderi(id, GL_COMPILE_STATUS) == GL_FALSE) throw new IllegalStateException("Infinity shader compile: " + glGetShaderInfoLog(id));
        return id;
    }
    private static int newTexture() {
        int id = glGenTextures(); glActiveTexture(GL_TEXTURE0); glBindTexture(GL_TEXTURE_2D, id);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR); glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE); glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
        return id;
    }
    int texture() { return texture; }
    void render(ProgressSnapshot state, long nowNanos, ResponsiveLayout layout) {
        if (closed) return;
        // Match FML's external render() contract while preserving more GL state than the stock implementation.
        int oldRead = glGetInteger(GL_READ_FRAMEBUFFER_BINDING), oldDraw = glGetInteger(GL_DRAW_FRAMEBUFFER_BINDING);
        int oldVao = glGetInteger(GL_VERTEX_ARRAY_BINDING), oldVbo = glGetInteger(GL_ARRAY_BUFFER_BINDING), oldProgram = glGetInteger(GL_CURRENT_PROGRAM);
        int oldActive = glGetInteger(GL_ACTIVE_TEXTURE);
        int[] viewport = new int[4]; glGetIntegerv(GL_VIEWPORT, viewport);
        float[] clearColor = new float[4]; glGetFloatv(GL_COLOR_CLEAR_VALUE, clearColor);
        boolean blend = glIsEnabled(GL_BLEND), depth = glIsEnabled(GL_DEPTH_TEST), cull = glIsEnabled(GL_CULL_FACE), scissor = glIsEnabled(GL_SCISSOR_TEST);
        int unpackBuffer = glGetInteger(GL_PIXEL_UNPACK_BUFFER_BINDING);
        int blendEquationRgb = glGetInteger(GL_BLEND_EQUATION_RGB), blendEquationAlpha = glGetInteger(GL_BLEND_EQUATION_ALPHA);
        int srcRgb = glGetInteger(GL_BLEND_SRC_RGB), dstRgb = glGetInteger(GL_BLEND_DST_RGB), srcA = glGetInteger(GL_BLEND_SRC_ALPHA), dstA = glGetInteger(GL_BLEND_DST_ALPHA);
        glActiveTexture(GL_TEXTURE0); int oldTexture = glGetInteger(GL_TEXTURE_BINDING_2D);
        try {
            glBindBuffer(GL_PIXEL_UNPACK_BUFFER, 0);
            if (width != layout.pixelWidth() || height != layout.pixelHeight()) {
                width = layout.pixelWidth(); height = layout.pixelHeight();
                glBindTexture(GL_TEXTURE_2D, texture);
                glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, (ByteBuffer) null);
            }
            glBindFramebuffer(GL_FRAMEBUFFER, fbo); glViewport(0, 0, width, height);
            glDisable(GL_DEPTH_TEST); glDisable(GL_CULL_FACE); glDisable(GL_SCISSOR_TEST);
            glBindBuffer(GL_PIXEL_UNPACK_BUFFER, 0); glBlendEquation(GL_FUNC_ADD);
            glEnable(GL_BLEND); glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
            glClearColor(0.018f, 0.024f, 0.039f, 1); glClear(GL_COLOR_BUFFER_BIT);
            glUseProgram(program); glUniform2f(sizeUniform, (float) layout.width(), (float) layout.height()); glUniform1i(glGetUniformLocation(program, "image"), 0);
            glBindVertexArray(vao); glBindBuffer(GL_ARRAY_BUFFER, vbo);
            vertices.clear();
            rect((float) layout.margin(), (float) layout.headerLine(), (float) layout.contentWidth(), 1, .17f, .23f, .31f, .35f);
            rect((float) layout.margin(), (float) layout.footerLine(), (float) layout.contentWidth(), 1, .17f, .23f, .31f, .35f);
            double seconds = reducedMotion ? 0 : (nowNanos - startNanos) / 1.0e9;
            // Quiet orbital accent around the supplied infinity-cube icon. Animation carries no work-count semantics.
            for (int i = 0; i < 192; i++) {
                double t0 = i * Math.PI * 2 / 192, t1 = (i + 1) * Math.PI * 2 / 192;
                float x0 = (float) (layout.centerX() + layout.iconSize() * .70 * Math.cos(t0)), y0 = (float) (layout.iconTop() + layout.iconSize() * .5 + layout.iconSize() * .5 * Math.sin(t0));
                float x1 = (float) (layout.centerX() + layout.iconSize() * .70 * Math.cos(t1)), y1 = (float) (layout.iconTop() + layout.iconSize() * .5 + layout.iconSize() * .5 * Math.sin(t1));
                float accent = reducedMotion ? .12f : (float) (.07 + .2 * Math.pow((1 + Math.cos(t0 - seconds * .55)) / 2, 10));
                line(x0, y0, x1, y1, 1.2f, .36f, .75f, .85f, accent);
            }
            float barX = (float) layout.barX(), barY = (float) layout.barY(), barWidth = (float) layout.barWidth();
            rect(barX, barY, barWidth, 3, .16f, .22f, .29f, .85f);
            if (state.status().equals("failed")) rect(barX, barY, barWidth, 3, .98f, .38f, .36f, 1);
            else if (state.determinate()) rect(barX, barY, (float) (barWidth * state.fraction()), 3, .37f, .79f, .92f, 1);
            else if (reducedMotion) {
                for (int i = 0; i < 3; i++) rect((float) layout.centerX() - 11 + i * 9, barY - 1, 4, 5, .37f, .79f, .92f, .8f);
            } else {
                float accentWidth = Math.min(62, barWidth * .15f);
                float x = barX + (float) ((Math.sin(seconds * .8) + 1) * .5) * (barWidth - accentWidth);
                rect(x, barY, accentWidth, 3, .37f, .79f, .92f, .8f);
            }
            draw(false);
            if (!sameText(state, textState) || !layout.equals(textLayout)) {
                uploadText(textCanvas.render(state, reducedMotion, layout)); textState = state; textLayout = layout;
            }
            vertices.clear(); quad(0, 0, (float) layout.width(), (float) layout.height(), 1, 1, 1, 1); glBindTexture(GL_TEXTURE_2D, textTexture); draw(true);
        } finally {
            glBindTexture(GL_TEXTURE_2D, oldTexture); glActiveTexture(oldActive);
            glUseProgram(oldProgram); glBindVertexArray(oldVao); glBindBuffer(GL_ARRAY_BUFFER, oldVbo);
            glBindFramebuffer(GL_READ_FRAMEBUFFER, oldRead); glBindFramebuffer(GL_DRAW_FRAMEBUFFER, oldDraw);
            glViewport(viewport[0], viewport[1], viewport[2], viewport[3]);
            glClearColor(clearColor[0], clearColor[1], clearColor[2], clearColor[3]);
            toggle(GL_BLEND, blend); toggle(GL_DEPTH_TEST, depth); toggle(GL_CULL_FACE, cull); toggle(GL_SCISSOR_TEST, scissor);
            glBlendFuncSeparate(srcRgb, dstRgb, srcA, dstA);
            glBlendEquationSeparate(blendEquationRgb, blendEquationAlpha); glBindBuffer(GL_PIXEL_UNPACK_BUFFER, unpackBuffer);
        }
    }
    private static boolean sameText(ProgressSnapshot a, ProgressSnapshot b) {
        return b != null && a.heading().equals(b.heading()) && a.detail().equals(b.detail());
    }
    private static void toggle(int capability, boolean enabled) { if (enabled) glEnable(capability); else glDisable(capability); }
    private void uploadText(BufferedImage image) {
        ByteBuffer pixels = textPixels; pixels.clear();
        int[] colors = ((java.awt.image.DataBufferInt) image.getRaster().getDataBuffer()).getData();
        for (int i = 0; i < width * height; i++) {
            int argb = colors[i];
            pixels.put((byte) (argb >> 16)).put((byte) (argb >> 8)).put((byte) argb).put((byte) (argb >> 24));
        }
        pixels.flip(); glBindTexture(GL_TEXTURE_2D, textTexture);
        int alignment = glGetInteger(GL_UNPACK_ALIGNMENT), rowLength = glGetInteger(GL_UNPACK_ROW_LENGTH);
        int skipRows = glGetInteger(GL_UNPACK_SKIP_ROWS), skipPixels = glGetInteger(GL_UNPACK_SKIP_PIXELS);
        try {
            glPixelStorei(GL_UNPACK_ALIGNMENT, 1); glPixelStorei(GL_UNPACK_ROW_LENGTH, 0);
            glPixelStorei(GL_UNPACK_SKIP_ROWS, 0); glPixelStorei(GL_UNPACK_SKIP_PIXELS, 0);
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, pixels);
        } finally {
            glPixelStorei(GL_UNPACK_ALIGNMENT, alignment); glPixelStorei(GL_UNPACK_ROW_LENGTH, rowLength);
            glPixelStorei(GL_UNPACK_SKIP_ROWS, skipRows); glPixelStorei(GL_UNPACK_SKIP_PIXELS, skipPixels);
        }
    }
    private void draw(boolean textured) {
        int count = vertices.position() / 8; vertices.flip(); glBufferData(GL_ARRAY_BUFFER, vertices, GL_STREAM_DRAW);
        glUniform1i(texturedUniform, textured ? 1 : 0); glDrawArrays(GL_TRIANGLES, 0, count);
    }
    private void rect(float x, float y, float w, float h, float r, float g, float b, float a) { quad(x, y, x + w, y + h, r, g, b, a); }
    private void quad(float x0, float y0, float x1, float y1, float r, float g, float b, float a) {
        vertex(x0,y0,0,0,r,g,b,a); vertex(x1,y0,1,0,r,g,b,a); vertex(x0,y1,0,1,r,g,b,a);
        vertex(x0,y1,0,1,r,g,b,a); vertex(x1,y0,1,0,r,g,b,a); vertex(x1,y1,1,1,r,g,b,a);
    }
    private void line(float x0, float y0, float x1, float y1, float width, float r, float g, float b, float a) {
        float d = (float) Math.hypot(x1-x0, y1-y0), nx = -(y1-y0) * width / (2*d), ny = (x1-x0) * width / (2*d);
        vertex(x0+nx,y0+ny,0,0,r,g,b,a); vertex(x1+nx,y1+ny,0,0,r,g,b,a); vertex(x0-nx,y0-ny,0,0,r,g,b,a);
        vertex(x0-nx,y0-ny,0,0,r,g,b,a); vertex(x1+nx,y1+ny,0,0,r,g,b,a); vertex(x1-nx,y1-ny,0,0,r,g,b,a);
    }
    private void vertex(float x,float y,float u,float v,float r,float g,float b,float a) {
        vertices.put(x).put(y).put(u).put(v).put(r).put(g).put(b).put(a);
    }
    void present(int framebufferWidth, int framebufferHeight) {
        if (closed || framebufferWidth <= 0 || framebufferHeight <= 0) return;
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, 0); glBindFramebuffer(GL_READ_FRAMEBUFFER, fbo);
        // The scene itself has reflowed to the viewport. Fill it, without fixed-aspect letterboxing.
        glBlitFramebuffer(0, height, width, 0, 0, 0, framebufferWidth, framebufferHeight, GL_COLOR_BUFFER_BIT, GL_LINEAR);
        glBindFramebuffer(GL_FRAMEBUFFER, 0);
    }
    /** Explicit in-app QA export of our real GL framebuffer, not a screenshot of another app. */
    void exportFrame(java.nio.file.Path destination) throws java.io.IOException {
        int oldRead = glGetInteger(GL_READ_FRAMEBUFFER_BINDING), oldPack = glGetInteger(GL_PIXEL_PACK_BUFFER_BINDING);
        int alignment = glGetInteger(GL_PACK_ALIGNMENT), rowLength = glGetInteger(GL_PACK_ROW_LENGTH);
        int skipRows = glGetInteger(GL_PACK_SKIP_ROWS), skipPixels = glGetInteger(GL_PACK_SKIP_PIXELS);
        ByteBuffer pixels = ByteBuffer.allocateDirect(width * height * 4);
        try {
            glBindFramebuffer(GL_READ_FRAMEBUFFER, fbo); glBindBuffer(GL_PIXEL_PACK_BUFFER, 0); glPixelStorei(GL_PACK_ALIGNMENT, 1);
            glPixelStorei(GL_PACK_ROW_LENGTH, 0); glPixelStorei(GL_PACK_SKIP_ROWS, 0); glPixelStorei(GL_PACK_SKIP_PIXELS, 0);
            glReadPixels(0, 0, width, height, GL_RGBA, GL_UNSIGNED_BYTE, pixels);
            BufferedImage result = new BufferedImage(width, height, BufferedImage.TYPE_INT_ARGB);
            for (int y = 0; y < height; y++) for (int x = 0; x < width; x++) {
                int offset = (y * width + x) * 4;
                int r = pixels.get(offset) & 255, g = pixels.get(offset+1) & 255, b = pixels.get(offset+2) & 255;
                result.setRGB(x, y, 0xff000000 | r << 16 | g << 8 | b);
            }
            java.nio.file.Files.createDirectories(destination.toAbsolutePath().getParent());
            if (!javax.imageio.ImageIO.write(result, "png", destination.toFile())) throw new java.io.IOException("PNG encoder unavailable");
        } finally {
            glBindFramebuffer(GL_READ_FRAMEBUFFER, oldRead); glBindBuffer(GL_PIXEL_PACK_BUFFER, oldPack); glPixelStorei(GL_PACK_ALIGNMENT, alignment);
            glPixelStorei(GL_PACK_ROW_LENGTH, rowLength); glPixelStorei(GL_PACK_SKIP_ROWS, skipRows); glPixelStorei(GL_PACK_SKIP_PIXELS, skipPixels);
        }
    }
    @Override public void close() {
        if (closed) return; closed = true;
        glDeleteTextures(textTexture); glDeleteTextures(texture); glDeleteFramebuffers(fbo);
        glDeleteBuffers(vbo); glDeleteVertexArrays(vao); glDeleteProgram(program);
    }
}
