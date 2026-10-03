package org.sinytra.connector.quilt;

import org.quiltmc.loader.api.*;
import java.nio.file.Path;
import java.util.*;

/** Descriptor of the API supplied by this host; not a separately loaded Quilt engine. */
final class QuiltLoaderProvider implements ModContainer {
    private final ModMetadata metadata = new ModMetadata() {
        public String id() { return "quilt_loader"; }
        public String group() { return "org.quiltmc"; }
        public Version version() { return Version.of("0.30.1"); }
        public String name() { return "Quilt Loader API compatibility provider"; }
        public String description() { return "Host-backed native-quilt-v1 API profile; does not provide the Quilt Loader engine or full 0.30.1 behavior."; }
        public Collection<ModLicense> licenses() { return List.of(ModLicense.fromIdentifierOrDefault("Apache-2.0")); }
        public Collection<ModContributor> contributors() { return List.of(); }
        public String getContactInfo(String key) { return null; }
        public Map<String, String> contactInfo() { return Map.of(); }
        public Collection<ModDependency> depends() { return List.of(); }
        public Collection<ModDependency> breaks() { return List.of(); }
        public String icon(int size) { return null; }
        public boolean containsValue(String key) { return false; }
        public LoaderValue value(String key) { return null; }
        public Map<String, LoaderValue> values() { return Map.of(); }
    };
    public ModMetadata metadata() { return metadata; }
    public Path rootPath() { throw new UnsupportedOperationException("The builtin Quilt API compatibility provider has no independent resource root"); }
    public List<List<Path>> getSourcePaths() { return List.of(); }
    public BasicSourceType getSourceType() { return BasicSourceType.BUILTIN; }
    public ClassLoader getClassLoader() { return null; }
}
