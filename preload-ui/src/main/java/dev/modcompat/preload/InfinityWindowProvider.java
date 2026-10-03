package dev.modcompat.preload;

import java.lang.reflect.Method;
import java.nio.file.Path;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;
import java.util.function.Consumer;
import java.util.function.IntConsumer;
import java.util.function.IntSupplier;
import java.util.function.LongSupplier;
import java.util.function.Supplier;
import net.neoforged.fml.earlydisplay.ColourScheme;
import net.neoforged.fml.earlydisplay.DisplayWindow;
import net.neoforged.fml.earlydisplay.RenderElement;
import net.neoforged.fml.loading.FMLConfig;
import org.lwjgl.glfw.GLFWVidMode;
import org.lwjgl.opengl.GL;
import org.lwjgl.opengl.GLCapabilities;
import static org.lwjgl.glfw.GLFW.*;

/**
 * FML 4.0.42 early-window SPI. Inherits DisplayWindow only for the public type
 * expected by NeoForgeLoadingOverlay; none of its default initialization,
 * artwork, render scheduler, shaders or rendering methods are called.
 */
public final class InfinityWindowProvider extends DisplayWindow {
    public static final String NAME = "unifiedinfinity";
    private final ReentrantLock renderLock = new ReentrantLock();
    private final boolean reducedMotion = Boolean.getBoolean("unified.infinity.reducedMotion");
    private final FramePacer pacer = new FramePacer(reducedMotion);
    private volatile RenderElement.DisplayContext displayContext = new RenderElement.DisplayContext(
            TextLayer.WIDTH, TextLayer.HEIGHT, 1, null, ColourScheme.BLACK, null);
    private final ProgressFileReader progress = new ProgressFileReader(progressPath(), System.currentTimeMillis() - 2_000);
    private final ProgressSampler sampler = new ProgressSampler(progress);
    private final ResponsivenessStats responsiveness = new ResponsivenessStats();
    private record Surface(int width, int height, int framebufferWidth, int framebufferHeight, boolean iconified) {
        boolean drawable() { return !iconified && ResponsiveLayout.drawable(width, height, framebufferWidth, framebufferHeight); }
    }
    private volatile Surface surface = new Surface(960, 540, 960, 540, false);
    private Thread mainThread;
    private ScheduledExecutorService scheduler;
    private GLCapabilities capabilities;
    private InfinityRenderer renderer;
    private volatile boolean handedOff, overlayActive, closed, disabled, stoppingRendering;
    private volatile Throwable renderFailure;
    private long handle;
    private String glVersion = "0.0";
    private int width = 960, height = 540, x, y, fbWidth = 960, fbHeight = 540;
    private Method overlayFactory;
    private final QaRecorder qa = new QaRecorder(optionalPath("unified.infinity.qaDirectory"));
    private volatile ProgressSnapshot lastRenderedSnapshot = ProgressSnapshot.WAITING;

    private static Path progressPath() {
        return optionalPath("unified.infinity.progressFile");
    }
    private static Path optionalPath(String property) {
        String value = System.getProperty(property);
        if (value == null || value.isBlank()) return null;
        try { return Path.of(value).toAbsolutePath().normalize(); }
        catch (RuntimeException ignored) { return null; }
    }
    @Override public String name() { return NAME; }
    @Override public Runnable initialize(String[] args) {
        if (mainThread != null) throw new IllegalStateException("Infinity provider already initialized");
        mainThread = Thread.currentThread();
        disabled = graphicsDisabled(args);
        if (disabled) return () -> { };
        width = argumentInt(args, "--width", 960); height = argumentInt(args, "--height", 540);
        try {
            initWindow(null);
            glfwMakeContextCurrent(handle); capabilities = GL.createCapabilities(); glfwSwapInterval(0);
            renderer = new InfinityRenderer(reducedMotion);
            sampler.start();
            Surface initial = surface;
            long now = System.nanoTime();
            if (initial.drawable() && pacer.due(now)) paintAndPresent(now, initial);
            qa.event("initialized", null);
            glfwMakeContextCurrent(0); GL.setCapabilities(null);
            scheduler = Executors.newSingleThreadScheduledExecutor(r -> {
                Thread t = new Thread(r, "unified-infinity-preload"); t.setDaemon(true); return t;
            });
            scheduler.scheduleWithFixedDelay(this::backgroundFrame, 0, pacer.intervalNanos(), TimeUnit.NANOSECONDS);
            return this::periodicTick;
        } catch (RuntimeException | LinkageError failure) {
            // Do not terminate GLFW globally: it may have been initialized by the host.
            sampler.close();
            if (handle != 0) {
                glfwMakeContextCurrent(handle);
                if (renderer != null) renderer.close();
                glfwMakeContextCurrent(0); glfwDestroyWindow(handle); handle = 0;
            }
            closed = true;
            throw new IllegalStateException("Unified Infinity could not initialize its early window", failure);
        }
    }
    static boolean graphicsDisabled(String[] args) {
        // java.awt.headless governs AWT widgets, not GLFW. Minecraft may set it even with a native display.
        return Boolean.getBoolean("unified.infinity.headless") || serverTarget(args);
    }
    private static boolean serverTarget(String[] args) {
        for (int i = 0; i + 1 < args.length; i++) if (args[i].equals("--launchTarget")) return args[i+1].toLowerCase(java.util.Locale.ROOT).contains("server");
        return false;
    }
    private static int argumentInt(String[] args, String name, int fallback) {
        for (int i = 0; i + 1 < args.length; i++) if (args[i].equals(name)) {
            try { return Math.max(320, Math.min(3840, Integer.parseInt(args[i+1]))); }
            catch (NumberFormatException ignored) { return fallback; }
        }
        return fallback;
    }
    @Override public void initWindow(String ignoredMinecraftVersion) {
        requireMainThread();
        if (handle != 0) throw new IllegalStateException("Window already exists");
        if (!glfwInit()) throw new IllegalStateException("GLFW initialization failed; a working graphical display is required");
        List<String> skip;
        try { skip = FMLConfig.getListConfigValue(FMLConfig.ConfigValue.EARLY_WINDOW_SKIP_GL_VERSIONS); }
        catch (RuntimeException ignored) { skip = List.of(); } // Standalone contract harness has no FML config.
        for (int[] version : new int[][] {{4,6},{4,5},{4,3},{4,1},{4,0},{3,3},{3,2}}) {
            if (skip.contains(version[0] + "." + version[1])) continue;
            glfwDefaultWindowHints(); glfwWindowHint(GLFW_VISIBLE, GLFW_FALSE); glfwWindowHint(GLFW_RESIZABLE, GLFW_TRUE);
            glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, version[0]); glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, version[1]);
            glfwWindowHint(GLFW_OPENGL_PROFILE, GLFW_OPENGL_CORE_PROFILE); glfwWindowHint(GLFW_OPENGL_FORWARD_COMPAT, GLFW_TRUE);
            handle = glfwCreateWindow(width, height, "Unified ∞ Infinity · Loading", 0, 0);
            // Clear failed-attempt GLFW errors so Minecraft does not see them later.
            glfwGetError((org.lwjgl.PointerBuffer) null);
            if (handle != 0) break;
        }
        if (handle == 0) throw new IllegalStateException("No OpenGL 3.2+ core profile is available");
        glVersion = glfwGetWindowAttrib(handle, GLFW_CONTEXT_VERSION_MAJOR) + "." + glfwGetWindowAttrib(handle, GLFW_CONTEXT_VERSION_MINOR);
        long monitor = glfwGetPrimaryMonitor(); GLFWVidMode mode = monitor == 0 ? null : glfwGetVideoMode(monitor);
        if (mode != null) glfwSetWindowPos(handle, Math.max(0, (mode.width()-width)/2), Math.max(0, (mode.height()-height)/2));
        setOwnIcon();
        // Normal decorated, resizable window. This is not an exclusive-fullscreen request.
        glfwSetWindowSizeLimits(handle, 320, 320, GLFW_DONT_CARE, GLFW_DONT_CARE);
        glfwShowWindow(handle); glfwPollEvents(); refreshDimensions();
    }
    private void setOwnIcon() {
        var image = TextLayer.icon();
        java.nio.ByteBuffer pixels = java.nio.ByteBuffer.allocateDirect(image.getWidth() * image.getHeight() * 4);
        for (int y = 0; y < image.getHeight(); y++) for (int x = 0; x < image.getWidth(); x++) {
            int color = image.getRGB(x, y);
            pixels.put((byte) (color >> 16)).put((byte) (color >> 8)).put((byte) color).put((byte) (color >> 24));
        }
        pixels.flip();
        try (org.lwjgl.glfw.GLFWImage.Buffer icons = org.lwjgl.glfw.GLFWImage.malloc(1)) {
            icons.width(image.getWidth()).height(image.getHeight()).pixels(pixels); glfwSetWindowIcon(handle, icons);
        }
    }
    private void refreshDimensions() {
        int[] a = new int[1], b = new int[1];
        glfwGetWindowSize(handle, a, b); int currentWidth = a[0], currentHeight = b[0];
        if (currentWidth > 0 && currentHeight > 0) { width = currentWidth; height = currentHeight; }
        glfwGetWindowPos(handle, a, b); x = a[0]; y = b[0];
        glfwGetFramebufferSize(handle, a, b); int currentFbWidth = Math.max(0, a[0]), currentFbHeight = Math.max(0, b[0]);
        // Like pinned FML's resize callbacks, handoff reports the last valid nonzero size.
        // Rendering still sees the actual zero/iconified surface and must skip it.
        if (currentFbWidth > 0 && currentFbHeight > 0) { fbWidth = currentFbWidth; fbHeight = currentFbHeight; }
        surface = new Surface(currentWidth, currentHeight, currentFbWidth, currentFbHeight, glfwGetWindowAttrib(handle, GLFW_ICONIFIED) == GLFW_TRUE);
    }
    private void backgroundFrame() {
        if (!renderLock.tryLock()) return;
        try {
            if (stoppingRendering || handedOff || closed) return;
            try {
                Surface current = surface;
                long now = System.nanoTime();
                if (!current.drawable() || !pacer.due(now)) return;
                glfwMakeContextCurrent(handle); GL.setCapabilities(capabilities);
                paintAndPresent(now, current);
            } catch (RuntimeException | LinkageError failure) { renderFailure = failure; }
            finally { glfwMakeContextCurrent(0); GL.setCapabilities(null); }
        } finally { renderLock.unlock(); }
    }
    @Override public void periodicTick() {
        if (disabled || closed) return;
        requireMainThread();
        if (renderFailure != null) throw new IllegalStateException("Infinity rendering failed", renderFailure);
        // GLFW polling and geometry queries are main-thread-only. Neither waits for the render lock.
        // In particular a driver-stalled background swap must not delay the next host event pump.
        glfwPollEvents(); responsiveness.poll(System.nanoTime()); refreshDimensions();
        if (glfwWindowShouldClose(handle)) throw new IllegalStateException("Startup cancelled by closing the loading window");
        if (handedOff && !overlayActive) {
            // Handoff already stopped background ownership; only this thread can render now.
            Surface current = surface;
            if (current.drawable() && pacer.due(System.nanoTime())) paintAndPresent(System.nanoTime(), current);
        }
    }
    @Override public long setupMinecraftWindow(IntSupplier expectedWidth, IntSupplier expectedHeight, Supplier<String> title, LongSupplier monitor) {
        requireMainThread();
        if (disabled) throw new IllegalStateException("A headless provider cannot create the Minecraft client window");
        if (closed || handedOff) throw new IllegalStateException("Invalid or repeated Minecraft window handoff");
        stopBackgroundFrames();
        acquireRenderOwnership(true);
        try {
            handedOff = true;
            // Acquired lock proves the last background frame released the context.
            glfwMakeContextCurrent(handle); GL.setCapabilities(capabilities); glfwSwapInterval(0);
            refreshDimensions(); glfwSetWindowTitle(handle, title.get());
            // The host owns its size/fullscreen rules after transfer.
            glfwSetWindowSizeLimits(handle, GLFW_DONT_CARE, GLFW_DONT_CARE, GLFW_DONT_CARE, GLFW_DONT_CARE);
            qa.event("window-context-handed-off", null);
            return handle;
        } finally { renderLock.unlock(); }
    }
    @Override public boolean positionWindow(Optional<Object> monitor, IntConsumer widthSetter, IntConsumer heightSetter, IntConsumer xSetter, IntConsumer ySetter) {
        if (disabled) return false;
        widthSetter.accept(width); heightSetter.accept(height); xSetter.accept(x); ySetter.accept(y); return true;
    }
    @Override public void updateFramebufferSize(IntConsumer widthSetter, IntConsumer heightSetter) {
        if (!disabled) { widthSetter.accept(fbWidth); heightSetter.accept(fbHeight); }
    }
    @Override public void updateModuleReads(ModuleLayer layer) {
        if (disabled) return; // Never attempt to load client classes on a server.
        Module game = layer.findModule("neoforge").orElseThrow(() -> new IllegalStateException("NeoForge GAME layer missing"));
        getClass().getModule().addReads(game);
        try {
            Class<?> overlay = Class.forName(game, "net.neoforged.neoforge.client.loading.NeoForgeLoadingOverlay");
            if (overlay == null) throw new ClassNotFoundException("NeoForgeLoadingOverlay");
            overlayFactory = overlay.getMethod("newInstance", Supplier.class, Supplier.class, Consumer.class, DisplayWindow.class);
            qa.event("game-overlay-contract-bound", null);
        } catch (ReflectiveOperationException e) { throw new IllegalStateException("NeoForge 21.1.219 overlay bridge contract changed", e); }
    }
    @SuppressWarnings("unchecked")
    @Override public <T> Supplier<T> loadingOverlay(Supplier<?> mc, Supplier<?> reload, Consumer<Optional<Throwable>> completion, boolean fade) {
        if (!handedOff || overlayFactory == null) throw new IllegalStateException("Overlay requested before GAME layer / window handoff");
        overlayActive = true;
        try {
            Consumer<Optional<Throwable>> observedCompletion = result -> {
                qa.event(result.isPresent() ? "host-reload-failed" : "host-reload-succeeded", null);
                qa.capture(result.isPresent() ? "host-reload-failed" : "host-reload-succeeded", lastRenderedSnapshot, renderer::exportFrame);
                completion.accept(result);
            };
            Supplier<T> factory = (Supplier<T>) overlayFactory.invoke(null, mc, reload, observedCompletion, this);
            return () -> {
                T overlay = factory.get();
                qa.event("game-overlay-created", null);
                return overlay;
            };
        }
        catch (ReflectiveOperationException e) { throw new IllegalStateException("Unable to create NeoForge reload-lifecycle bridge", e); }
    }
    @Override public void render(int alpha) {
        requireMainThread();
        if (!closed && renderer != null) {
            refreshDimensions();
            Surface current = surface;
            if (current.drawable()) {
                // Reflow on the next paced frame, including during resize: reduced motion remains capped at 10 Hz.
                if (pacer.due(System.nanoTime())) {
                    long start = System.nanoTime(); paintFrame(start, current); responsiveness.frame(start, System.nanoTime());
                    if (overlayActive) qa.capture("game-overlay-rendering", lastRenderedSnapshot, renderer::exportFrame);
                }
            }
        }
        // NeoForge applies alpha to the texture during compositing; it passes 255 here.
    }
    @Override public void addMojangTexture(int textureId) { /* Own visual design; upstream lifecycle bridge calls this hook. */ }
    @Override public int getFramebufferTextureId() { if (renderer == null) throw new IllegalStateException("Framebuffer not initialized"); return renderer.texture(); }
    @Override public RenderElement.DisplayContext context() { return displayContext; }
    @Override public String getGLVersion() { return glVersion; }
    @Override public Runnable start(String minecraftVersion, String forgeVersion) { throw new UnsupportedOperationException("Use the ImmediateWindowProvider initialize entry point"); }
    @Override public void close() {
        if (closed) return;
        if (renderer != null) requireMainThread();
        stopBackgroundFrames(); sampler.close();
        acquireRenderOwnership(false);
        try {
            if (closed) return;
            closed = true;
            if (renderer != null) {
                glfwMakeContextCurrent(handle); GL.setCapabilities(capabilities); renderer.close();
                if (!handedOff) { glfwMakeContextCurrent(0); GL.setCapabilities(null); glfwDestroyWindow(handle); handle = 0; }
            }
            qa.event("closed-render-resources", null);
            // The handed-off GLFW window belongs to Minecraft. Never destroy it or globally terminate GLFW.
        } finally { renderLock.unlock(); }
    }
    private void stopBackgroundFrames() {
        stoppingRendering = true;
        if (scheduler != null) scheduler.shutdown();
    }
    private void acquireRenderOwnership(boolean cancellable) {
        // Handoff/cleanup must await the current GL owner; never take a context away from a live frame.
        // While waiting, the main thread remains an event pump. A wedged driver fails explicitly after 5s.
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        boolean interrupted = false;
        try {
            while (!renderLock.tryLock()) {
                if (System.nanoTime() >= deadline)
                    throw new IllegalStateException("Timed out waiting for Infinity GL ownership; context not transferred or destroyed");
                if (!disabled && handle != 0) {
                    requireMainThread(); glfwPollEvents(); responsiveness.poll(System.nanoTime()); refreshDimensions();
                    if (cancellable && glfwWindowShouldClose(handle))
                        throw new IllegalStateException("Startup cancelled during loading-window handoff");
                }
                try { TimeUnit.MILLISECONDS.sleep(10); }
                catch (InterruptedException e) { interrupted = true; }
            }
        } finally { if (interrupted) Thread.currentThread().interrupt(); }
    }
    public void exportFrameForQa(Path destination) throws java.io.IOException {
        requireMainThread();
        if (!handedOff || closed || renderer == null) throw new IllegalStateException("QA export requires active main-thread context");
        // Main-thread-only after transfer; the worker no longer owns the context.
        renderer.exportFrame(destination);
    }
    private void paintAndPresent(long now, Surface current) {
        long begin = System.nanoTime();
        paintFrame(now, current);
        renderer.present(current.framebufferWidth(), current.framebufferHeight()); glfwSwapBuffers(handle);
        responsiveness.frame(begin, System.nanoTime());
    }
    private void paintFrame(long now, Surface current) {
        ProgressSnapshot snapshot = sampler.latest();
        ResponsiveLayout layout = ResponsiveLayout.of(current.width(), current.height(), current.framebufferWidth(), current.framebufferHeight());
        renderer.render(snapshot, now, layout);
        lastRenderedSnapshot = snapshot;
        // Use exact framebuffer aspect for the pinned NeoForge compositor; texture pixels may be bounded below it.
        // scale=1 and matching aspect make its min(wscale,hscale) cover the entire native framebuffer.
        if (displayContext.width() != current.framebufferWidth() || displayContext.height() != current.framebufferHeight())
            displayContext = new RenderElement.DisplayContext(current.framebufferWidth(), current.framebufferHeight(), 1, null, ColourScheme.BLACK, null);
        qa.captureSource(snapshot, renderer::exportFrame);
    }
    public String diagnostics() {
        return responsiveness.summary() + " telemetryReads=" + progress.reads() + " qaSynchronous=" + qa.enabled();
    }
    @Override public void crash(String message) { System.err.println("Unified Infinity startup error: " + message); }
    private void requireMainThread() {
        if (mainThread == null || Thread.currentThread() != mainThread) throw new IllegalStateException("GLFW lifecycle operation must run on startup main thread");
    }
}
