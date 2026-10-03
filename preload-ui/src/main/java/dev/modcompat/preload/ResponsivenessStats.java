package dev.modcompat.preload;

/** Constant-space observations, not a claim of input-to-present latency or GPU execution time. */
final class ResponsivenessStats {
    private long frames, totalFrameNanos, maxFrameNanos, lastFrame, maxFrameGap, longFrames;
    private long polls, lastPoll, maxPollGap;
    private final long[] frameGaps = new long[512], pollGaps = new long[512];
    private long frameGapCount, pollGapCount;
    synchronized void frame(long start, long end) {
        long duration = Math.max(0, end - start);
        frames++; totalFrameNanos += duration; maxFrameNanos = Math.max(maxFrameNanos, duration);
        if (lastFrame != 0) {
            long gap = Math.max(0, start - lastFrame); maxFrameGap = Math.max(maxFrameGap, gap);
            frameGaps[(int) (frameGapCount++ % frameGaps.length)] = gap;
            if (gap > 100_000_000L) longFrames++;
        }
        lastFrame = start;
    }
    synchronized void poll(long now) {
        if (lastPoll != 0) {
            long gap = Math.max(0, now - lastPoll); maxPollGap = Math.max(maxPollGap, gap);
            pollGaps[(int) (pollGapCount++ % pollGaps.length)] = gap;
        }
        lastPoll = now; polls++;
    }
    synchronized String summary() {
        return "frames=" + frames + " frameWorkMeanMs=" + (frames == 0 ? 0 : totalFrameNanos / 1e6 / frames)
                + " frameWorkMaxMs=" + maxFrameNanos / 1e6 + " frameGapMaxMs=" + maxFrameGap / 1e6
                + " frameGapsOver100ms=" + longFrames + " frameGapRollingP95Ms=" + percentile(frameGaps, frameGapCount, .95)
                + " frameGapRollingP99Ms=" + percentile(frameGaps, frameGapCount, .99)
                + " eventPolls=" + polls + " eventPollGapMaxMs=" + maxPollGap / 1e6
                + " eventPollGapRollingP95Ms=" + percentile(pollGaps, pollGapCount, .95);
    }
    private static double percentile(long[] ring, long observations, double fraction) {
        int count = (int) Math.min(ring.length, observations);
        if (count == 0) return 0;
        long[] copy = java.util.Arrays.copyOf(ring, count); java.util.Arrays.sort(copy);
        return copy[Math.max(0, (int) Math.ceil(count * fraction) - 1)] / 1e6;
    }
}
