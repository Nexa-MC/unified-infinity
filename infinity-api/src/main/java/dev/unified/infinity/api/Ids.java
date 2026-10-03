package dev.unified.infinity.api;

import java.util.Objects;

final class Ids {
    private Ids() { }

    static String requireNamespaced(String id) {
        Objects.requireNonNull(id, "id");
        if (!id.matches("[a-z0-9_.-]+:[a-z0-9_./-]+")) {
            throw new IllegalArgumentException("Expected namespaced id, got: " + id);
        }
        return id;
    }
}
