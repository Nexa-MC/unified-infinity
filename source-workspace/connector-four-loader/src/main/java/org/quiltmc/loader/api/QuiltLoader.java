/*
 * Adapted for the native-quilt-v1 host compatibility profile (2026).
 * Loader-engine references are replaced by isolated host-backed/value implementations.
 * Copyright 2016 FabricMC
 * Copyright 2022-2023 QuiltMC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package org.quiltmc.loader.api;

import net.fabricmc.loader.api.FabricLoader;
import net.fabricmc.loader.api.ObjectShare;
import org.quiltmc.loader.api.entrypoint.EntrypointContainer;
import org.quiltmc.loader.api.entrypoint.EntrypointException;
import org.sinytra.connector.quilt.QuiltBridge;

import java.nio.file.Path;
import java.util.*;

/** Binary-compatible static facade for the native-quilt-v1 host profile, not a Quilt engine. */
public final class QuiltLoader {
    private QuiltLoader() {}
    public static <T> List<T> getEntrypoints(String key, Class<T> type) throws EntrypointException {
        List<T> result = new ArrayList<>();
        QuiltBridge.invokeContainer(key, type, c -> result.add(c.getEntrypoint()));
        return List.copyOf(result);
    }
    public static <T> List<EntrypointContainer<T>> getEntrypointContainers(String key, Class<T> type) throws EntrypointException {
        return QuiltBridge.entrypoints(key, type);
    }
    public static MappingResolver getMappingResolver() {
        var host = FabricLoader.getInstance().getMappingResolver();
        return new MappingResolver() {
            public Collection<String> getNamespaces() { return host.getNamespaces(); }
            public String getCurrentRuntimeNamespace() { return host.getCurrentRuntimeNamespace(); }
            public String mapClassName(String ns, String name) { return host.mapClassName(ns, name); }
            public String unmapClassName(String ns, String name) { return host.unmapClassName(ns, name); }
            public String mapFieldName(String ns, String owner, String name, String desc) { return host.mapFieldName(ns, owner, name, desc); }
            public String mapMethodName(String ns, String owner, String name, String desc) { return host.mapMethodName(ns, owner, name, desc); }
        };
    }
    public static Optional<ModContainer> getModContainer(String id) { return QuiltBridge.findMod(id); }
    public static Collection<ModContainer> getAllMods() { return QuiltBridge.allMods(); }
    public static boolean isModLoaded(String id) { return getModContainer(id).isPresent(); }
    public static Optional<ModContainer> getModContainer(Class<?> clazz) {
        if (clazz.getName().startsWith("org.quiltmc.loader.api.") && clazz.getClassLoader() == QuiltLoader.class.getClassLoader()) return getModContainer("quilt_loader");
        var source = clazz.getProtectionDomain().getCodeSource();
        if (source == null) return Optional.empty();
        String location = source.getLocation().toExternalForm();
        for (var mod : getAllMods()) {
            if (mod.getSourceType() == ModContainer.BasicSourceType.BUILTIN) continue;
            try {
                String root = mod.rootPath().toUri().toString();
                if (root.equals(location) || root.startsWith("jar:" + location + "!/")) return Optional.of(mod);
            } catch (RuntimeException ignored) { }
        }
        return Optional.empty();
    }
    public static boolean isDevelopmentEnvironment() { return FabricLoader.getInstance().isDevelopmentEnvironment(); }
    @Deprecated public static Object getGameInstance() { return FabricLoader.getInstance().getGameInstance(); }
    public static String getNormalizedGameVersion() {
        return FabricLoader.getInstance().getModContainer("minecraft").orElseThrow().getMetadata().getVersion().getFriendlyString();
    }
    public static String getRawGameVersion() { return FabricLoader.getInstance().getRawGameVersion(); }
    public static Path getGameDir() { return FabricLoader.getInstance().getGameDir(); }
    public static Path getCacheDir() {
        Path path = getGameDir().resolve(".cache");
        try { return java.nio.file.Files.createDirectories(path); }
        catch (java.io.IOException e) { throw new java.io.UncheckedIOException("Cannot create host game cache directory " + path, e); }
    }
    public static Path getConfigDir() { return FabricLoader.getInstance().getConfigDir(); }
    public static Path getGlobalCacheDir() { throw unsupported("global cache directories"); }
    public static Path getGlobalConfigDir() { throw unsupported("global configuration directories"); }
    public static boolean globalDirsEnabled() { return false; }
    public static String[] getLaunchArguments(boolean sanitize) { return FabricLoader.getInstance().getLaunchArguments(sanitize); }
    public static ObjectShare getObjectShare() { return FabricLoader.getInstance().getObjectShare(); }
    public static String createModTable() {
        StringBuilder result = new StringBuilder("Mod ID | Version | Source\n");
        for (var mod : getAllMods()) result.append(mod.metadata().id()).append(" | ").append(mod.metadata().version().raw()).append(" | ").append(mod.getSourceType()).append('\n');
        return result.toString();
    }
    private static UnsupportedOperationException unsupported(String feature) {
        return new UnsupportedOperationException("Native Quilt first slice does not support " + feature);
    }
}
