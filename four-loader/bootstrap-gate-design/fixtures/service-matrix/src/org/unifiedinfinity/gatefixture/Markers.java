package org.unifiedinfinity.gatefixture;

import java.io.IOException;
import java.nio.file.*;
final class Markers {
    static void mark(String phase) {
        String value = System.getProperty("unified.gate.fixture.markers");
        if (value == null) throw new IllegalStateException("Fixture requires a test-owned marker directory");
        try {
            Path root = Path.of(value).toRealPath();
            Files.writeString(root.resolve(phase), "executed\n", StandardOpenOption.CREATE_NEW);
        } catch (IOException e) { throw new IllegalStateException(e); }
    }
}
