package dev.modcompat.preload;

/** Independent render and I/O clocks: animation never increments a work counter. */
public final class FramePacer {
    private final long interval;
    private long next;
    public FramePacer(boolean reducedMotion) { interval = 1_000_000_000L / (reducedMotion ? 10 : 30); }
    public boolean due(long nanos) {
        if (nanos < next) return false;
        next = nanos + interval;
        return true;
    }
    public long intervalNanos() { return interval; }
}
