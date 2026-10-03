package org.sinytra.connector.transformer.quilt;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/** Original archive provenance for explicitly managed embedded modules, not a discovery registry. */
public final class NativeQuiltSources {
    private static final Map<Path, List<Path>> CHAINS = new ConcurrentHashMap<>();
    private NativeQuiltSources() {}
    public static void record(Path extracted, List<Path> chain) {
        Path key = extracted.toAbsolutePath().normalize();
        List<Path> value = List.copyOf(chain);
        List<Path> old = CHAINS.putIfAbsent(key, value);
        if (old != null && !old.equals(value)) throw new IllegalArgumentException("Conflicting native Quilt embedded provenance for " + extracted);
    }
    public static List<Path> chain(String source) { return CHAINS.getOrDefault(Path.of(source).toAbsolutePath().normalize(), List.of()); }
}
