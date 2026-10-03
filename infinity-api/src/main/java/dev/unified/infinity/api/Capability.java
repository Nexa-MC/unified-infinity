package dev.unified.infinity.api;

/** A host-declared feature requirement, not a JVM security permission. */
public record Capability(String id) {
    public Capability {
        Ids.requireNamespaced(id);
    }
}
