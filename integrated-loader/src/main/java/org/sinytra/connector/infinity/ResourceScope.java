package org.sinytra.connector.infinity;

import java.util.ArrayDeque;

/** Locator-thread ownership of resources created by this transaction, never borrowed handles. */
public final class ResourceScope implements AutoCloseable {
    private final ArrayDeque<AutoCloseable> resources = new ArrayDeque<>();
    private boolean closed;

    public <T extends AutoCloseable> T own(T resource) {
        if (closed) throw new IllegalStateException("Resource scope already closed");
        resources.addLast(resource);
        return resource;
    }

    @Override
    public void close() {
        if (closed) return;
        closed = true;
        RuntimeException failure = null;
        while (!resources.isEmpty()) {
            try {
                resources.removeLast().close();
            } catch (Exception exception) {
                if (failure == null) failure = new RuntimeException("Failed to close owned transform resources", exception);
                else failure.addSuppressed(exception);
            }
        }
        if (failure != null) throw failure;
    }
}
