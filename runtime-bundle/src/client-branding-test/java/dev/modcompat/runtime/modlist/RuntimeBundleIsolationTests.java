package dev.modcompat.runtime.modlist;

import java.io.File;
import java.lang.reflect.InvocationTargetException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.Arrays;

/** Common linkage must not resolve any Minecraft/client UI class merely to construct the product. */
public final class RuntimeBundleIsolationTests {
    public static void main(String[] args) throws Exception {
        URL[] urls = Arrays.stream(System.getProperty("java.class.path").split(java.util.regex.Pattern.quote(File.pathSeparator)))
            .map(value -> {
                try { return Path.of(value).toUri().toURL(); }
                catch (Exception e) { throw new IllegalArgumentException(e); }
            }).toArray(URL[]::new);
        try (URLClassLoader isolated = new URLClassLoader(urls, ClassLoader.getPlatformClassLoader()) {
            @Override protected Class<?> loadClass(String name, boolean resolve) throws ClassNotFoundException {
                if (name.startsWith("net.minecraft.client.") || name.startsWith("dev.modcompat.runtime.modlist."))
                    throw new ClassNotFoundException("Client class linkage forbidden by common-product regression: " + name);
                return super.loadClass(name, resolve);
            }
        }) {
            Class<?> product = Class.forName("dev.modcompat.runtime.bundle.RuntimeBundle", true, isolated);
            Object instance = product.getConstructor().newInstance();
            if (product.getDeclaredAnnotations().length != 0) throw new AssertionError("Common product must have no mod annotation");
            Class<?> phase = Class.forName("net.neoforged.fml.loading.unified.GameCompatibilityComponent$LifecyclePhase", true, isolated);
            Object loadComplete = Arrays.stream(phase.getEnumConstants()).filter(value -> value.toString().equals("LOAD_COMPLETE")).findFirst().orElseThrow();
            try {
                product.getMethod("onLifecycle", phase).invoke(instance, loadComplete);
                throw new AssertionError("Lifecycle before loader initialization was accepted");
            } catch (InvocationTargetException expected) {
                if (!(expected.getCause() instanceof IllegalStateException)
                    || !expected.getCause().getMessage().contains("before FML initialization")) throw expected;
            }
            System.out.println("PASS: inert internal product construction and lifecycle guard without client-class linkage");
        }
    }
}
