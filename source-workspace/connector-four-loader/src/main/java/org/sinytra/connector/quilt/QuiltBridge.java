package org.sinytra.connector.quilt;

import net.fabricmc.loader.api.FabricLoader;
import org.quiltmc.loader.api.ModContainer;
import org.quiltmc.loader.api.entrypoint.EntrypointContainer;
import org.quiltmc.loader.api.entrypoint.EntrypointException;

import java.nio.file.Path;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.BiConsumer;
import java.util.function.Consumer;

/** Native Quilt API views over the single FFLoader host. Does not discover, solve or instantiate mods. */
public final class QuiltBridge {
    public static final String METADATA_KEY = "infinity:quilt_metadata";
    public static final String SOURCE_KEY = "infinity:quilt_source";
    public static final String SOURCE_CHAIN_KEY = "infinity:quilt_source_chain";
    private static final Map<net.fabricmc.loader.api.ModContainer, QuiltModContainer> VIEWS = Collections.synchronizedMap(new IdentityHashMap<>());
    private static final Map<String, Path> SOURCES = new ConcurrentHashMap<>();
    private static volatile ClassLoader hostTargetClassLoader;
    private static volatile Map<String, Integer> resolvedOrder = Map.of();
    private static final Set<String> STARTED_STAGES = new HashSet<>();
    private static final Map<String, Throwable> FAILED_STAGES = new HashMap<>();
    private static final ModContainer LOADER_PROVIDER = new QuiltLoaderProvider();
    private QuiltBridge() {}

    public static QuiltModContainer wrap(net.fabricmc.loader.api.ModContainer host) {
        return VIEWS.computeIfAbsent(host, QuiltModContainer::new);
    }
    public static void recordSource(String originalId, Path source) {
        Path previous = SOURCES.putIfAbsent(originalId, source.toAbsolutePath().normalize());
        if (previous != null && !previous.equals(source.toAbsolutePath().normalize()))
            throw new IllegalStateException("Multiple original Quilt input paths for " + originalId + ": " + previous + " and " + source);
    }
    static Path recordedSource(String id) { return SOURCES.get(id); }
    static boolean isBuiltinProvider(String id) { return id.equals("quilt_loader"); }

    static ClassLoader targetClassLoader() {
        ClassLoader pinned = hostTargetClassLoader;
        return pinned == null ? net.fabricmc.loader.impl.launch.FabricLauncherBase.getLauncher().getTargetClassLoader() : pinned;
    }

    /** Capture the selected native order from the existing single ModResolver, before any lifecycle stage. */
    public static synchronized void recordResolvedOrder(List<String> originalIds) {
        if (!STARTED_STAGES.isEmpty()) throw new IllegalStateException("Cannot change native Quilt order after lifecycle dispatch");
        Map<String, Integer> order = new LinkedHashMap<>();
        for (String id : originalIds) if (order.putIfAbsent(id, order.size()) != null)
            throw new IllegalArgumentException("Duplicate native Quilt resolved provider " + id);
        resolvedOrder = Map.copyOf(order);
    }
    private static int bootstrapPriority(String key, EntrypointContainer<?> entry) {
        // The original pinned QSL base RegistriesMixin is deliberately suppressed.
        // Its EventRegistry init owns automatic-listener registration, so this one
        // existing init dispatch must initialize that bootstrap provider before consumers.
        return key.equals("init") && entry.getProvider().metadata() instanceof QuiltModMetadata metadata
            && metadata.nativeQuilt() && metadata.id().equals("quilt_base") ? 0 : 1;
    }
    private static int resolvedPriority(EntrypointContainer<?> entry) {
        return resolvedOrder.getOrDefault(entry.getProvider().metadata().id(), Integer.MAX_VALUE);
    }

    public static Collection<ModContainer> allMods() {
        List<ModContainer> result = new ArrayList<>();
        for (var host : FabricLoader.getInstance().getAllMods()) result.add(wrap(host));
        if (result.stream().noneMatch(mod -> mod.metadata().id().equals("quilt_loader"))) result.add(LOADER_PROVIDER);
        return List.copyOf(result);
    }
    public static Optional<ModContainer> findMod(String id) {
        for (ModContainer mod : allMods()) if (mod.metadata().id().equals(id)) return Optional.of(mod);
        return FabricLoader.getInstance().getModContainer(id).map(QuiltBridge::wrap);
    }
    public static <T> List<EntrypointContainer<T>> entrypoints(String key, Class<T> type) {
        try {
            return FabricLoader.getInstance().getEntrypointContainers(key, type).stream().map(host -> (EntrypointContainer<T>) new EntrypointContainer<T>() {
                public T getEntrypoint() {
                    try { return host.getEntrypoint(); }
                    catch (Throwable t) { throw failure(key, getProvider(), t); }
                }
                public ModContainer getProvider() { return wrap(host.getProvider()); }
                public String getDefinition() { return host.getDefinition(); }
            }).sorted(Comparator.<EntrypointContainer<T>>comparingInt(entry -> bootstrapPriority(key, entry))
                .thenComparingInt(QuiltBridge::resolvedPriority)).toList();
            // Stream sorting is stable: original per-provider entrypoint array order is unchanged.
        } catch (EntrypointException e) { throw e; }
        catch (Throwable e) { throw failure(key, null, e); }
    }
    public static <T> void invokeContainer(String key, Class<T> type, Consumer<EntrypointContainer<T>> consumer) {
        EntrypointException failure = null;
        for (var entrypoint : entrypoints(key, type)) {
            try { consumer.accept(entrypoint); }
            catch (Throwable t) {
                var error = failure(key, entrypoint.getProvider(), t);
                if (failure == null) failure = error;
                else failure.addSuppressed(error);
            }
        }
        if (failure != null) throw failure;
    }
    /** Stage owner marks before callbacks. Re-entry is a no-op; failed stages retain their failure and never replay. */
    public static synchronized <T> void invokeOnce(String stage, Class<T> type, BiConsumer<T, ModContainer> consumer) {
        // The FFLoader accessor follows the calling thread's context. Retain the
        // actual existing game loader at the host-controlled launch boundary so
        // later metadata reads on worker threads cannot change container identity.
        if (hostTargetClassLoader == null) hostTargetClassLoader = Objects.requireNonNull(
            net.fabricmc.loader.impl.launch.FabricLauncherBase.getLauncher().getTargetClassLoader(), "Host game classloader");
        if (FAILED_STAGES.containsKey(stage)) throw failure(stage, null, FAILED_STAGES.get(stage));
        if (!STARTED_STAGES.add(stage)) return;
        try { invokeContainer(stage, type, entry -> consumer.accept(entry.getEntrypoint(), entry.getProvider())); }
        catch (Throwable t) { FAILED_STAGES.put(stage, t); throw t; }
    }
    private static EntrypointException failure(String key, ModContainer provider, Throwable cause) {
        String context = provider == null ? "host entrypoint store" : provider.metadata().id();
        if (provider != null) {
            try { context += " from " + provider.getSourcePaths(); } catch (RuntimeException ignored) { /* Preserve the original failure. */ }
        }
        return new HostEntrypointException(key, "Quilt entrypoint '" + key + "' failed for " + context, cause);
    }
    private static final class HostEntrypointException extends EntrypointException {
        private final String key;
        private HostEntrypointException(String key, String message, Throwable cause) { super(message, cause); this.key = key; }
        public String getKey() { return key; }
    }
}
