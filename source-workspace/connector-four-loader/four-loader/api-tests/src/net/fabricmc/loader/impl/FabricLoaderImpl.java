package net.fabricmc.loader.impl;

import net.fabricmc.api.EnvType;
import net.fabricmc.loader.api.*;
import net.fabricmc.loader.api.entrypoint.EntrypointContainer;
import java.io.File;
import java.nio.file.Path;
import java.util.*;
import java.util.function.Consumer;

/** Test-only host. Shadows no shipped source and never starts FFLoader/FML. */
public final class FabricLoaderImpl implements FabricLoader {
    public static final FabricLoaderImpl INSTANCE = new FabricLoaderImpl();
    public final List<ModContainer> mods = new ArrayList<>();
    public final Map<String, List<EntrypointContainer<?>>> entries = new HashMap<>();
    public int reads;
    @SuppressWarnings("unchecked") public <T> List<EntrypointContainer<T>> getEntrypointContainers(String key, Class<T> type) { reads++; return (List) entries.getOrDefault(key, List.of()); }
    public <T> List<T> getEntrypoints(String key, Class<T> type) { return getEntrypointContainers(key,type).stream().map(EntrypointContainer::getEntrypoint).toList(); }
    public <T> void invokeEntrypoints(String key, Class<T> type, Consumer<? super T> c) { getEntrypoints(key,type).forEach(c); }
    public ObjectShare getObjectShare() { return null; }
    public MappingResolver getMappingResolver() { return new MappingResolver() {
        public Collection<String> getNamespaces(){return List.of("intermediary", "named");}
        public String getCurrentRuntimeNamespace(){return "named";}
        public String mapClassName(String ns,String n){return "mapped."+n;}
        public String unmapClassName(String ns,String n){return "unmapped."+n;}
        public String mapFieldName(String ns,String o,String n,String d){return "field_"+n;}
        public String mapMethodName(String ns,String o,String n,String d){return "method_"+n;}
    }; }
    public Collection<ModContainer> getAllMods(){return mods;}
    public Optional<ModContainer> getModContainer(String id){return mods.stream().filter(m->m.getMetadata().getId().equals(id)).findFirst();}
    public boolean isModLoaded(String id){return getModContainer(id).isPresent();}
    public boolean isDevelopmentEnvironment(){return false;}
    public EnvType getEnvironmentType(){return EnvType.SERVER;}
    public String getRawGameVersion(){return "1.21.1";}
    public Object getGameInstance(){return null;}
    public Path getGameDir(){return Path.of("/test/game");}
    public File getGameDirectory(){return getGameDir().toFile();}
    public Path getConfigDir(){return getGameDir().resolve("config");}
    public File getConfigDirectory(){return getConfigDir().toFile();}
    public String[] getLaunchArguments(boolean sanitize){return new String[]{sanitize ? "sanitized" : "raw"};}
}
