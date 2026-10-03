package dev.modcompat.preload;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.lwjgl.glfw.Callbacks;
import org.lwjgl.glfw.GLFW;
import org.lwjgl.opengl.GL;
import org.lwjgl.opengl.GL32C;
import org.sinytra.connector.infinity.BoundedBatch;

/** Interactive native QA of the frozen candidate JAR, not Minecraft or loader-event acceptance. */
public final class ResponsiveNativeHarness {
    private static final long DEADLINE_NANOS = TimeUnit.SECONDS.toNanos(120);
    private static final ArrayBlockingQueue<String> COMMANDS = new ArrayBlockingQueue<>(16);
    private static final CountDownLatch RELEASE_WORK = new CountDownLatch(1);
    private static long start, handle;
    private static boolean handedOff, requestedClose, reduced;
    private static InfinityWindowProvider provider;
    private static final java.nio.ByteBuffer WINDOW_PIXELS = java.nio.ByteBuffer.allocateDirect(2048 * 2048 * 4);

    public static void main(String[] args) throws Exception {
        start = System.nanoTime(); reduced = Boolean.getBoolean("unified.infinity.reducedMotion");
        Files.createDirectories(Path.of("frames"));
        provider = new InfinityWindowProvider();
        Thread commands = new Thread(() -> {
            Path inbox = Path.of("qa-command.txt");
            while (System.nanoTime() - start < DEADLINE_NANOS) {
                try {
                    if (Files.isRegularFile(inbox) && Files.size(inbox) <= 512) {
                        for (String line : Files.readAllLines(inbox)) {
                            if (!COMMANDS.offer(line.strip())) System.out.println("HARNESS_COMMAND_QUEUE_FULL");
                        }
                        Files.deleteIfExists(inbox);
                    }
                    Thread.sleep(50);
                } catch (java.io.IOException ignored) { }
                catch (InterruptedException stopped) { return; }
            }
        }, "infinity-native-qa-control");
        commands.setDaemon(true); commands.start();
        Throwable failure = null;
        try {
            provider.initialize(new String[] {"--launchTarget", "forgeclient", "--width", "1180", "--height", "812"});
            handle = field(provider, "handle", Long.class);
            testTitle("测试阶段：后台等待与窗口交互；未启动加载器");
            GLFW.glfwSetWindowSizeCallback(handle, (window, width, height) -> event("window-size", width + "x" + height));
            GLFW.glfwSetFramebufferSizeCallback(handle, (window, width, height) -> event("framebuffer-size", width + "x" + height));
            GLFW.glfwSetWindowPosCallback(handle, (window, x, y) -> event("window-position", x + "," + y));
            GLFW.glfwSetWindowIconifyCallback(handle, (window, iconified) -> event("iconified", Boolean.toString(iconified)));
            GLFW.glfwSetWindowCloseCallback(handle, window -> event("native-close", "requested"));
            GLFW.glfwSetKeyCallback(handle, (window, key, scancode, action, mods) -> {
                if (key == GLFW.GLFW_KEY_ESCAPE && action == GLFW.GLFW_PRESS) {
                    event("native-key-cancel", "Escape"); GLFW.glfwSetWindowShouldClose(window, true);
                }
            });
            mark("pre-handoff-ready");
            System.out.println("HARNESS_SYNTHETIC_WAIT no loader events are generated; use CUA for window actions, QA control 'handoff' releases synthetic work");
            BoundedBatch.map(List.of(1), 1, Duration.ofSeconds(110), value -> {
                RELEASE_WORK.await(); return value;
            }, () -> tick(true));
            long transferred = provider.setupMinecraftWindow(() -> 1180, () -> 812,
                    () -> "预载交互测试（未启动游戏）｜测试阶段：图形上下文交接完成", () -> 0);
            if (transferred != handle || GLFW.glfwGetCurrentContext() != handle)
                throw new AssertionError("Same-window/current-context handoff failed");
            handedOff = true;
            System.out.println("HARNESS_HANDOFF_PASSED renderer=" + GL32C.glGetString(GL32C.GL_RENDERER));
            mark("post-handoff-ready");
            capture(reduced ? "reduced-first" : "baseline-1180x812");
            while (System.nanoTime() - start < DEADLINE_NANOS) { tick(false); Thread.sleep(8); }
            throw new AssertionError("Native QA deadline reached without a real window close");
        } catch (Throwable thrown) {
            requestedClose = handle != 0 && GLFW.glfwWindowShouldClose(handle);
            if (requestedClose && thrown instanceof IllegalStateException
                    && thrown.getMessage().startsWith("Startup cancelled")) {
                System.out.println("HARNESS_REAL_CLOSE_OBSERVED phase=" + (handedOff ? "after-handoff" : "before-handoff"));
            } else { failure = thrown; throw thrown; }
        } finally {
            RELEASE_WORK.countDown();
            System.out.println("HARNESS_DIAGNOSTICS " + provider.diagnostics());
            if (handle != 0) Callbacks.glfwFreeCallbacks(handle);
            int texture = handedOff ? provider.getFramebufferTextureId() : 0;
            provider.close(); provider.close();
            if (handedOff) {
                if (GLFW.glfwGetCurrentContext() != handle || GL32C.glIsTexture(texture))
                    throw new AssertionError("Provider resource cleanup/context ownership failed");
                GLFW.glfwMakeContextCurrent(0); GL.setCapabilities(null); GLFW.glfwDestroyWindow(handle);
                System.out.println("HARNESS_GL_RESOURCES_CLOSED host-owned window survived provider close, then harness destroyed it");
            } else if (field(provider, "handle", Long.class) != 0L || GLFW.glfwGetCurrentContext() != 0L) {
                throw new AssertionError("Early-window close did not release provider-owned window");
            }
            long until = System.nanoTime() + TimeUnit.SECONDS.toNanos(2);
            while (ownedWorkersAlive() && System.nanoTime() < until) Thread.sleep(10);
            if (ownedWorkersAlive()) throw new AssertionError("Render, telemetry, or transform worker leaked");
            GLFW.glfwTerminate();
            System.out.println("HARNESS_CLEANUP_PASSED requestedClose=" + requestedClose + " failure=" + (failure != null));
        }
        System.out.println("HARNESS_COMPLETE native-only; no Minecraft/client/mod lifecycle tested");
    }

    private static void tick(boolean waiting) {
        if (System.nanoTime() - start > DEADLINE_NANOS) throw new IllegalStateException("Native QA deadline exceeded");
        provider.periodicTick();
        if (waiting && !System.getProperty("unified.infinity.qaScenario", "normal").equals("early-close")
                && System.nanoTime() - start > TimeUnit.SECONDS.toNanos(8)) RELEASE_WORK.countDown();
        for (String command; (command = COMMANDS.poll()) != null;) {
            if (command.equals("handoff") && waiting) RELEASE_WORK.countDown();
            else if (command.startsWith("mark ")) mark(command.substring(5));
            else if (command.startsWith("resize ")) {
                String[] size = command.substring(7).split("x");
                if (size.length != 2) throw new IllegalArgumentException("Expected resize WIDTHxHEIGHT");
                int width = Integer.parseInt(size[0]), height = Integer.parseInt(size[1]);
                if (width < 320 || width > 1364 || height < 320 || height > 1024) throw new IllegalArgumentException("Resize outside native QA bounds");
                event("programmatic-native-resize-request", width + "x" + height); GLFW.glfwSetWindowSize(handle, width, height);
                testTitle("测试阶段：程序化调整窗口 " + width + "×" + height + "；未启动加载器");
            }
            else if (command.equals("minimize")) { event("programmatic-native-iconify-request", ""); testTitle("测试阶段：最小化检查"); GLFW.glfwIconifyWindow(handle); }
            else if (command.equals("restore")) { event("programmatic-native-restore-request", ""); GLFW.glfwRestoreWindow(handle); testTitle("测试阶段：恢复窗口；按 Esc 结束测试"); }
            else if (command.startsWith("capture ") && handedOff) {
                try { capture(command.substring(8)); }
                catch (java.io.IOException e) { throw new RuntimeException(e); }
            } else System.out.println("HARNESS_COMMAND_REJECTED " + command);
        }
    }

    private static void capture(String label) throws java.io.IOException {
        label = safeLabel(label);
        Path destination = Path.of("frames", "scene-" + label + ".png");
        event("diagnostic-readback-begin", label);
        provider.exportFrameForQa(destination);
        var image = javax.imageio.ImageIO.read(destination.toFile());
        int rgb = image.getRGB(0, 0) & 0xffffff;
        int[] corners = {image.getRGB(image.getWidth() - 1, 0), image.getRGB(0, image.getHeight() - 1),
                image.getRGB(image.getWidth() - 1, image.getHeight() - 1)};
        if (rgb == 0 || java.util.Arrays.stream(corners).anyMatch(color -> (color & 0xffffff) != rgb))
            throw new AssertionError("Scene background is black or does not cover all corners");
        mark("capture-" + label);
        System.out.println("HARNESS_FRAME " + destination + " raster=" + image.getWidth() + "x" + image.getHeight() + " cornerRGB=" + Integer.toHexString(rgb));
        capturePresentedWindow(Path.of("frames", "window-preswap-" + label + ".png"));
        event("diagnostic-readback-end", label);
        if (reduced && label.equals("reduced-second")) {
            if (!java.util.Arrays.equals(Files.readAllBytes(Path.of("frames", "scene-reduced-first.png")), Files.readAllBytes(destination)))
                throw new AssertionError("Reduced-motion frame changed without events or geometry changes");
            if (!java.util.Arrays.equals(Files.readAllBytes(Path.of("frames", "window-preswap-reduced-first.png")), Files.readAllBytes(Path.of("frames", "window-preswap-reduced-second.png"))))
                throw new AssertionError("Reduced-motion presented window changed without events or geometry changes");
            System.out.println("HARNESS_REDUCED_MOTION_IDENTICAL_PASSED");
        }
    }

    /** Actual default/back framebuffer, immediately before the known swap; excludes OS borders and pointer. */
    private static void capturePresentedWindow(Path destination) throws java.io.IOException {
        if (!handedOff || GLFW.glfwGetCurrentContext() != handle) throw new AssertionError("Unsafe window readback owner");
        int[] width = new int[1], height = new int[1]; GLFW.glfwGetFramebufferSize(handle, width, height);
        int w = width[0], h = height[0];
        if (w <= 0 || h <= 0 || (long) w * h * 4 > WINDOW_PIXELS.capacity()) throw new AssertionError("Window capture outside QA memory bound");
        try {
            // On this composited llvmpipe desktop GL_FRONT readback returned all black despite visible output.
            // Exercise the candidate's unchanged presentation function, then capture the real drawable before swap.
            GL32C.glBindFramebuffer(GL32C.GL_DRAW_FRAMEBUFFER, 0); GL32C.glDrawBuffer(GL32C.GL_BACK);
            field(provider, "renderer", InfinityRenderer.class).present(w, h);
        } catch (ReflectiveOperationException e) { throw new java.io.IOException(e); }
        int read = GL32C.glGetInteger(GL32C.GL_READ_FRAMEBUFFER_BINDING), readBuffer = GL32C.glGetInteger(GL32C.GL_READ_BUFFER);
        int packBuffer = GL32C.glGetInteger(GL32C.GL_PIXEL_PACK_BUFFER_BINDING), alignment = GL32C.glGetInteger(GL32C.GL_PACK_ALIGNMENT);
        int row = GL32C.glGetInteger(GL32C.GL_PACK_ROW_LENGTH), skipRows = GL32C.glGetInteger(GL32C.GL_PACK_SKIP_ROWS), skipPixels = GL32C.glGetInteger(GL32C.GL_PACK_SKIP_PIXELS);
        try {
            GL32C.glBindFramebuffer(GL32C.GL_READ_FRAMEBUFFER, 0); GL32C.glReadBuffer(GL32C.GL_BACK);
            GL32C.glBindBuffer(GL32C.GL_PIXEL_PACK_BUFFER, 0); GL32C.glPixelStorei(GL32C.GL_PACK_ALIGNMENT, 1);
            GL32C.glPixelStorei(GL32C.GL_PACK_ROW_LENGTH, 0); GL32C.glPixelStorei(GL32C.GL_PACK_SKIP_ROWS, 0); GL32C.glPixelStorei(GL32C.GL_PACK_SKIP_PIXELS, 0);
            WINDOW_PIXELS.clear(); GL32C.glReadPixels(0, 0, w, h, GL32C.GL_RGBA, GL32C.GL_UNSIGNED_BYTE, WINDOW_PIXELS);
            if (GL32C.glGetError() != GL32C.GL_NO_ERROR) throw new AssertionError("Default framebuffer readback produced a GL error");
            var image = new java.awt.image.BufferedImage(w, h, java.awt.image.BufferedImage.TYPE_INT_RGB);
            for (int y = 0; y < h; y++) for (int x = 0; x < w; x++) {
                int offset = ((h - 1 - y) * w + x) * 4;
                image.setRGB(x, y, (WINDOW_PIXELS.get(offset) & 255) << 16 | (WINDOW_PIXELS.get(offset + 1) & 255) << 8 | (WINDOW_PIXELS.get(offset + 2) & 255));
            }
            if (!javax.imageio.ImageIO.write(image, "png", destination.toFile())) throw new java.io.IOException("PNG unavailable");
            int background = image.getRGB(0, 0) & 0xffffff;
            if (background == 0) throw new AssertionError("Presented window contains a black edge");
            for (int x = 0; x < w; x++) {
                if ((image.getRGB(x, 0) & 0xffffff) != background || (image.getRGB(x, h - 1) & 0xffffff) != background)
                    throw new AssertionError("Presented top/bottom edge does not have continuous scene background");
            }
            for (int y = 0; y < h; y++) {
                if ((image.getRGB(0, y) & 0xffffff) != background || (image.getRGB(w - 1, y) & 0xffffff) != background)
                    throw new AssertionError("Presented left/right edge does not have continuous scene background");
            }
            System.out.println("HARNESS_PRESENTED_WINDOW " + destination + " framebuffer=" + w + "x" + h + " source=GL_BACK/default/pre-swap excludesOSBorder=true");
            System.out.println("HARNESS_PRESENTED_EDGE_COVERAGE_PASSED backgroundRGB=" + Integer.toHexString(background));
            GLFW.glfwSwapBuffers(handle);
        } finally {
            GL32C.glBindFramebuffer(GL32C.GL_READ_FRAMEBUFFER, read); GL32C.glReadBuffer(readBuffer);
            GL32C.glBindBuffer(GL32C.GL_PIXEL_PACK_BUFFER, packBuffer); GL32C.glPixelStorei(GL32C.GL_PACK_ALIGNMENT, alignment);
            GL32C.glPixelStorei(GL32C.GL_PACK_ROW_LENGTH, row); GL32C.glPixelStorei(GL32C.GL_PACK_SKIP_ROWS, skipRows); GL32C.glPixelStorei(GL32C.GL_PACK_SKIP_PIXELS, skipPixels);
        }
    }

    private static void mark(String label) {
        int[] w = new int[1], h = new int[1], fw = new int[1], fh = new int[1];
        GLFW.glfwGetWindowSize(handle, w, h); GLFW.glfwGetFramebufferSize(handle, fw, fh);
        event("mark-" + safeLabel(label), "window=" + w[0] + "x" + h[0] + " framebuffer=" + fw[0] + "x" + fh[0]
                + " iconified=" + GLFW.glfwGetWindowAttrib(handle, GLFW.GLFW_ICONIFIED) + " " + provider.diagnostics());
    }
    private static String safeLabel(String value) { return value.replaceAll("[^a-zA-Z0-9_-]", "_"); }
    private static void testTitle(String phase) {
        GLFW.glfwSetWindowTitle(handle, "预载交互测试（未启动游戏）｜" + phase);
    }
    private static void event(String kind, String detail) {
        System.out.println("HARNESS_EVENT epochMs=" + System.currentTimeMillis() + " elapsedMs=" + (System.nanoTime() - start) / 1_000_000 + " kind=" + kind + " " + detail);
    }
    private static boolean ownedWorkersAlive() {
        return Thread.getAllStackTraces().keySet().stream().anyMatch(thread -> thread.isAlive()
                && (thread.getName().equals("unified-infinity-preload") || thread.getName().equals("unified-infinity-progress")
                || thread.getName().startsWith("infinity-jar-transform-")));
    }
    private static <T> T field(Object owner, String name, Class<T> type) throws ReflectiveOperationException {
        var field = owner.getClass().getDeclaredField(name); field.setAccessible(true); return type.cast(field.get(owner));
    }
}
