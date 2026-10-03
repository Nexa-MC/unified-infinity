package dev.modcompat.preload;

import org.lwjgl.glfw.GLFW;
import org.lwjgl.opengl.GL32C;

/** Native ABI smoke test only. Does not load Minecraft, mods, or produce progress events. */
public final class NativeHarness {
    public static void main(String[] args) throws Exception {
        InfinityWindowProvider provider = new InfinityWindowProvider();
        provider.initialize(new String[] {"--launchTarget", "forgeclient"});
        System.out.println("NATIVE_HARNESS_STARTED gl=" + provider.getGLVersion());
        long until = System.nanoTime() + 30_000_000_000L;
        long handoffAt = System.nanoTime() + 10_000_000_000L;
        long handle = 0;
        boolean reduced = Boolean.getBoolean("unified.infinity.reducedMotion");
        java.nio.file.Path frame = java.nio.file.Path.of(reduced ? "reports/native-framebuffer-reduced-motion.png" : "reports/native-framebuffer.png");
        long secondCaptureAt = handoffAt + 4_000_000_000L;
        boolean secondCaptured = false;
        boolean animation = Boolean.getBoolean("unified.infinity.qaAnimation");
        long animationStart = handoffAt + 500_000_000L, nextAnimation = animationStart;
        int animationIndex = 0;
        java.nio.file.Path animationDir = java.nio.file.Path.of("reports/native-animation-frames");
        if (animation) java.nio.file.Files.createDirectories(animationDir);
        try {
            while (System.nanoTime() < until) {
                provider.periodicTick();
                if (handle == 0 && System.nanoTime() >= handoffAt) {
                    handle = provider.setupMinecraftWindow(() -> 960, () -> 540, () -> "Unified Infinity · SPI handoff smoke test", () -> 0);
                    if (handle == 0 || GLFW.glfwGetCurrentContext() != handle) throw new AssertionError("Native context handoff failed");
                    System.out.println("NATIVE_HANDOFF_PASSED renderer=" + GL32C.glGetString(GL32C.GL_RENDERER));
                    provider.exportFrameForQa(frame);
                    System.out.println("QA_FRAME_EXPORTED " + frame + " (actual OpenGL framebuffer; no Minecraft)");
                }
                if (reduced && handle != 0 && !secondCaptured && System.nanoTime() >= secondCaptureAt) {
                    java.nio.file.Path second = java.nio.file.Path.of("reports/native-framebuffer-reduced-motion-second.png");
                    provider.exportFrameForQa(second);
                    if (!java.util.Arrays.equals(java.nio.file.Files.readAllBytes(frame), java.nio.file.Files.readAllBytes(second)))
                        throw new AssertionError("Reduced-motion output changed without a source event");
                    System.out.println("REDUCED_MOTION_STATIC_FRAME_PASSED separatedBySeconds=4");
                    secondCaptured = true;
                }
                long now = System.nanoTime();
                if (animation && handle != 0 && now >= nextAnimation && now < animationStart + 5_000_000_000L) {
                    String name = String.format(java.util.Locale.ROOT, "frame-%03d.png", animationIndex++);
                    provider.exportFrameForQa(animationDir.resolve(name));
                    java.nio.file.Files.writeString(animationDir.resolve("timing.csv"), name + "," + now + "\n",
                            java.nio.file.StandardOpenOption.CREATE, java.nio.file.StandardOpenOption.APPEND);
                    nextAnimation = now + 100_000_000L;
                }
                Thread.sleep(10);
            }
        } finally {
            System.out.println("NATIVE_DIAGNOSTICS " + provider.diagnostics());
            provider.close();
            if (handle != 0) GLFW.glfwDestroyWindow(handle);
        }
        System.out.println("NATIVE_HARNESS_COMPLETE no Minecraft/client/mod lifecycle was tested");
    }
}
