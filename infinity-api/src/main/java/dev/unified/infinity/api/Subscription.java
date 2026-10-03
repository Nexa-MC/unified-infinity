package dev.unified.infinity.api;

/** A thread-safe, idempotently closeable listener registration. */
public interface Subscription extends AutoCloseable {
    boolean isClosed();

    /** Removes the listener from future snapshots, without waiting for an active dispatch. */
    @Override
    void close();
}
