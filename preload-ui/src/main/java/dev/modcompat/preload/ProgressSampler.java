package dev.modcompat.preload;

import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/** One optional I/O worker, no queued polling backlog, and no reads on the GLFW/GL ownership path. */
final class ProgressSampler implements AutoCloseable {
    private final java.util.function.LongFunction<ProgressSnapshot> poller;
    private volatile ProgressSnapshot latest = ProgressSnapshot.WAITING;
    private ScheduledExecutorService executor;
    private boolean closed;
    ProgressSampler(ProgressFileReader reader) { this(reader::poll); }
    ProgressSampler(java.util.function.LongFunction<ProgressSnapshot> poller) {
        this.poller = java.util.Objects.requireNonNull(poller);
    }
    synchronized void start() {
        if (closed || executor != null) throw new IllegalStateException("Progress sampler already started or closed");
        executor = Executors.newSingleThreadScheduledExecutor(task -> {
            Thread thread = new Thread(task, "unified-infinity-progress"); thread.setDaemon(true); return thread;
        });
        executor.scheduleWithFixedDelay(() -> latest = poller.apply(System.nanoTime()),
                0, ProgressFileReader.POLL_NANOS, TimeUnit.NANOSECONDS);
    }
    ProgressSnapshot latest() { return latest; }
    @Override public synchronized void close() {
        // Never join a potentially slow filesystem operation on the startup/render thread.
        closed = true;
        if (executor != null) executor.shutdownNow();
    }
}
