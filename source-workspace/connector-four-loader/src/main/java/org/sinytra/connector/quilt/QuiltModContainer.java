package org.sinytra.connector.quilt;

import net.fabricmc.loader.api.metadata.CustomValue;
import net.fabricmc.loader.api.metadata.ModOrigin;
import org.quiltmc.loader.api.ModContainer;
import org.quiltmc.loader.api.ModMetadata;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

/** A view of an admitted host container, never a second mod registry or classloader. */
public final class QuiltModContainer implements ModContainer {
    private final net.fabricmc.loader.api.ModContainer host;
    private final QuiltModMetadata metadata;

    QuiltModContainer(net.fabricmc.loader.api.ModContainer host) {
        this.host = host;
        this.metadata = new QuiltModMetadata(host.getMetadata());
    }
    public net.fabricmc.loader.api.ModContainer host() { return host; }
    public ModMetadata metadata() { return metadata; }
    public Path rootPath() { return host.getRootPath(); }
    public BasicSourceType getSourceType() {
        if ("builtin".equals(host.getMetadata().getType()) || QuiltBridge.isBuiltinProvider(metadata.id())) return BasicSourceType.BUILTIN;
        return metadata.nativeQuilt() ? BasicSourceType.NORMAL_QUILT : BasicSourceType.NORMAL_FABRIC;
    }
    public ClassLoader getClassLoader() {
        return getSourceType() == BasicSourceType.BUILTIN ? null : QuiltBridge.targetClassLoader();
    }
    public List<List<Path>> getSourcePaths() {
        // Embedded managed payloads retain installation provenance independently
        // from their extracted, hash-verified transformer input and runtime root.
        CustomValue sourceChain = host.getMetadata().getCustomValue(QuiltBridge.SOURCE_CHAIN_KEY);
        if (sourceChain != null) {
            List<Path> chain = new ArrayList<>();
            for (CustomValue part : sourceChain.getAsArray()) {
                String path = part.getAsString();
                if (path.isBlank()) throw new IllegalStateException("Empty original Quilt source-chain path for " + metadata.id());
                chain.add(Path.of(path));
            }
            if (chain.isEmpty()) throw new IllegalStateException("Empty original Quilt source chain for " + metadata.id());
            return List.of(List.copyOf(chain));
        }
        CustomValue source = host.getMetadata().getCustomValue(QuiltBridge.SOURCE_KEY);
        if (source != null) return List.of(List.of(Path.of(source.getAsString())));
        Path recorded = QuiltBridge.recordedSource(metadata.id());
        if (recorded != null) return List.of(List.of(recorded));
        if (metadata.nativeQuilt()) throw new IllegalStateException("Missing original Quilt input source for " + metadata.id());
        var origin = host.getOrigin();
        if (origin.getKind() == ModOrigin.Kind.PATH) return origin.getPaths().stream().map(List::of).toList();
        if (origin.getKind() == ModOrigin.Kind.NESTED) {
            var parent = host.getContainingMod();
            if (parent.isPresent()) {
                List<List<Path>> result = new ArrayList<>();
                for (var chain : QuiltBridge.wrap(parent.get()).getSourcePaths()) {
                    List<Path> nested = new ArrayList<>(chain);
                    nested.add(Path.of(origin.getParentSubLocation()));
                    result.add(List.copyOf(nested));
                }
                return List.copyOf(result);
            }
        }
        return List.of();
    }
}
