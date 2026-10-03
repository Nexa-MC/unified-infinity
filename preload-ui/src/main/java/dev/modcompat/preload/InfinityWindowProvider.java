package dev.modcompat.preload;

import java.lang.reflect.Method;
import java.nio.file.Path;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
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
    private final Object renderLock = new Object();
    private final boolean reducedMotion = Boolean.getBoolean("unified.infinity.reducedMotion");
    private final FramePacer pacer = new FramePacer(reducedMotion);
    private final RenderElement.DisplayContext displayContext = new RenderElement.DisplayContext(
            TextLayer.WIDTH, TextLayer.HEIGHT, 1, null, ColourScheme.BLACK, null);
    private final ProgressFileReader progress = new ProgressFileReader(progressPath(), System.currentTimeMillis() - 2_000);
    private Thread mainThread;
    private ScheduledExecutorService scheduler;
    private GLCapabilities capabilities;
    private InfinityRenderer renderer;
    private volatile boolean handedOff, overlayActive, closed, disabled;
    private volatile Throwable renderFailure;
    private long handle;
    private String glVersion = "0.0";
    private int width = 960, height = 540, x, y, fbWidth = 960, fbHeight = 540;
    private Method overlayFactory;
    private final QaRecorder qa = new QaRecorder(optionalPath("unified.infinity.qaDirectory"));
    private long renderedFrames, renderCpuNanos, maxFrameCpuNanos;

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
            paintFrame(System.nanoTime()); renderer.present(fbWidth, fbHeight); glfwSwapBuffers(handle);
            qa.event("initialized", null);
            glfwMakeContextCurrent(0); GL.setCapabilities(null);
            scheduler = Executors.newSingleThreadScheduledExecutor(r -> {
                Thread t = new Thread(r, "unified-infinity-preload"); t.setDaemon(true); return t;
            });
            scheduler.scheduleWithFixedDelay(this::backgroundFrame, 0, pacer.intervalNanos(), TimeUnit.NANOSECONDS);
            return this::periodicTick;
        } catch (RuntimeException | LinkageError failure) {
            // Do not terminate GLFW globally: it may have been initialized by the host.
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
        setOwnIcon(); refreshDimensions(); glfwShowWindow(handle); glfwPollEvents();
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
        glfwGetWindowSize(handle, a, b); width = a[0]; height = b[0];
        glfwGetWindowPos(handle, a, b); x = a[0]; y = b[0];
        glfwGetFramebufferSize(handle, a, b); fbWidth = a[0]; fbHeight = b[0];
    }
    private void backgroundFrame() {
        synchronized (renderLock) {
            if (handedOff || closed) return;
            try {
                glfwMakeContextCurrent(handle); GL.setCapabilities(capabilities);
                long now = System.nanoTime();
                if (pacer.due(now) && fbWidth > 0 && fbHeight > 0) {
                    paintFrame(now); renderer.present(fbWidth, fbHeight); glfwSwapBuffers(handle);
                }
            } catch (RuntimeException | LinkageError failure) { renderFailure = failure; }
            finally { glfwMakeContextCurrent(0); GL.setCapabilities(null); }
        }
    }
    @Override public void periodicTick() {
        if (disabled || closed) return;
        requireMainThread();
        if (renderFailure != null) throw new IllegalStateException("Infinity rendering failed", renderFailure);
        glfwPollEvents();
        if (glfwWindowShouldClose(handle)) throw new IllegalStateException("Startup cancelled by closing the loading window");
        synchronized (renderLock) {
            refreshDimensions();
            if (handedOff && !overlayActive && pacer.due(System.nanoTime())) {
                paintFrame(System.nanoTime());
                renderer.present(fbWidth, fbHeight); glfwSwapBuffers(handle);
            }
        }
    }
    @Override public long setupMinecraftWindow(IntSupplier expectedWidth, IntSupplier expectedHeight, Supplier<String> title, LongSupplier monitor) {
        requireMainThread();
        if (disabled) throw new IllegalStateException("A headless provider cannot create the Minecraft client window");
        synchronized (renderLock) {
            if (closed || handedOff) throw new IllegalStateException("Invalid or repeated Minecraft window handoff");
            handedOff = true;
            if (scheduler != null) scheduler.shutdown();
            // Lock proves the last background frame released the context. Pending frames observe handedOff and do nothing.
            glfwMakeContextCurrent(handle); GL.setCapabilities(capabilities); glfwSwapInterval(0);
            refreshDimensions(); glfwSetWindowTitle(handle, title.get());
            qa.event("window-context-handed-off", null);
            return handle;
        }
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
                qa.capture(result.isPresent() ? "host-reload-failed" : "host-reload-succeeded", progress.poll(System.nanoTime()), renderer::exportFrame);
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
        if (!closed && renderer != null && pacer.due(System.nanoTime())) {
            paintFrame(System.nanoTime());
            if (overlayActive) qa.capture("game-overlay-rendering", progress.poll(System.nanoTime()), renderer::exportFrame);
        }
        // NeoForge applies alpha to the texture during compositing; it passes 255 here.
    }
    @Override public void addMojangTexture(int textureId) { /* Own visual design; upstream lifecycle bridge calls this hook. */ }
    @Override public int getFramebufferTextureId() { if (renderer == null) throw new IllegalStateException("Framebuffer not initialized"); return renderer.texture(); }
    @Override public RenderElement.DisplayContext context() { return displayContext; }
    @Override public String getGLVersion() { return glVersion; }
    @Override public Runnable start(String minecraftVersion, String forgeVersion) { throw new UnsupportedOperationException("Use the ImmediateWindowProvider initialize entry point"); }
    @Override public void close() {
        synchronized (renderLock) {
            if (closed) return;
            if (renderer != null) requireMainThread();
            closed = true; if (scheduler != null) scheduler.shutdown();
            if (renderer != null) {
                requireMainThread();
                glfwMakeContextCurrent(handle); GL.setCapabilities(capabilities); renderer.close();
                if (!handedOff) { glfwMakeContextCurrent(0); glfwDestroyWindow(handle); handle = 0; }
            }
            qa.event("closed-render-resources", null);
            // The handed-off GLFW window belongs to Minecraft. Never destroy it or globally terminate GLFW.
        }
    }
    public void exportFrameForQa(Path destination) throws java.io.IOException {
        requireMainThread();
        synchronized (renderLock) {
            if (!handedOff || closed || renderer == null) throw new IllegalStateException("QA export requires active main-thread context");
            renderer.exportFrame(destination);
        }
    }
    private void paintFrame(long now) {
        ProgressSnapshot snapshot = progress.poll(now);
        long begin = System.nanoTime();
        renderer.render(snapshot, now);
        recordFrame(System.nanoTime() - begin);
        qa.captureSource(snapshot, renderer::exportFrame);
    }
    private void recordFrame(long cpuNanos) {
        renderedFrames++; renderCpuNanos += cpuNanos; maxFrameCpuNanos = Math.max(maxFrameCpuNanos, cpuNanos);
    }
    public String diagnostics() {
        synchronized (renderLock) {
            return "frames=" + renderedFrames + " renderCpuMeanMs=" + (renderedFrames == 0 ? 0 : renderCpuNanos / 1e6 / renderedFrames)
                    + " renderCpuMaxMs=" + maxFrameCpuNanos / 1e6 + " telemetryReads=" + progress.reads();
        }
    }
    @Override public void crash(String message) { System.err.println("Unified Infinity startup error: " + message); }
    private void requireMainThread() {
        if (mainThread == null || Thread.currentThread() != mainThread) throw new IllegalStateException("GLFW lifecycle operation must run on startup main thread");
    }
}
