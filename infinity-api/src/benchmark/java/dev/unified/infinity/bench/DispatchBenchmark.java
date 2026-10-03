package dev.unified.infinity.bench;

import com.sun.management.ThreadMXBean;
import dev.unified.infinity.api.Capability;
import dev.unified.infinity.api.EventSource;
import dev.unified.infinity.api.ModScope;
import java.lang.management.ManagementFactory;
import java.util.Arrays;
import java.util.Locale;
import java.util.Set;

/** Local smoke measurement, deliberately not represented as JMH or game performance. */
public final class DispatchBenchmark {
    private static volatile long sink;
    private static final Capability TICK = new Capability("infinity:server_tick");
    private record Tick(long increment) { }
    private static final class Counter { long total; }

    public static void main(String[] args) {
        int warmup = Integer.getInteger("warmup", 1_000_000);
        int iterations = Integer.getInteger("iterations", 1_000_000);
        int rounds = Integer.getInteger("rounds", 7);
        if (warmup < 1 || iterations < 1 || rounds < 1) throw new IllegalArgumentException("positive counts required");
        ThreadMXBean allocation = allocationMeter();
        System.out.println("Local dispatch smoke measurement; NOT JMH; NOT Minecraft/TPS/FPS evidence");
        System.out.println("java=" + System.getProperty("java.runtime.version")
                + " vm=" + System.getProperty("java.vm.name")
                + " os=" + System.getProperty("os.name") + "/" + System.getProperty("os.arch"));
        System.out.println("warmup=" + warmup + " iterations/round=" + iterations + " rounds=" + rounds
                + " allocationMeter=" + (allocation == null ? "unavailable" : "HotSpot ThreadMXBean"));
        System.out.println("listeners,median_ns_per_dispatch,min_ns_per_dispatch,max_ns_per_dispatch,"
                + "min_alloc_bytes_per_round,max_alloc_bytes_per_round,median_bytes_per_dispatch");
        for (int count : new int[] {0, 1, 8, 64}) {
            measure(count, warmup, iterations, rounds, allocation);
        }
        System.out.println("checksum=" + sink);
        System.out.println("Same preallocated payload and nonallocating callbacks throughout measurement.");
        System.out.println("Registration/removal, payload creation, exceptions, and callback allocations are excluded.");
    }

    private static void measure(int count, int warmup, int iterations, int rounds, ThreadMXBean allocation) {
        EventSource<Tick> source = EventSource.onCurrentThread("infinity:bench", TICK);
        Counter[] counters = new Counter[count];
        Tick tick = new Tick(1);
        try (ModScope mod = ModScope.open("benchmark", Set.of(TICK))) {
            for (int i = 0; i < count; i++) {
                Counter counter = new Counter();
                counters[i] = counter;
                source.event().listen(mod, value -> counter.total += value.increment());
            }
            dispatch(source, tick, warmup);
            long[] nanos = new long[rounds];
            long[] bytes = new long[rounds];
            long threadId = Thread.currentThread().threadId();
            for (int round = 0; round < rounds; round++) {
                long beforeBytes = allocation == null ? -1 : allocation.getThreadAllocatedBytes(threadId);
                long start = System.nanoTime();
                dispatch(source, tick, iterations);
                long elapsed = System.nanoTime() - start;
                long afterBytes = allocation == null ? -1 : allocation.getThreadAllocatedBytes(threadId);
                nanos[round] = elapsed;
                bytes[round] = allocation == null ? -1 : afterBytes - beforeBytes;
            }
            long expected = (long) warmup + (long) iterations * rounds;
            long checksum = 0;
            for (Counter counter : counters) {
                if (counter.total != expected) throw new AssertionError("callback count differs");
                checksum += counter.total;
            }
            sink = checksum;
            Arrays.sort(nanos);
            Arrays.sort(bytes);
            System.out.printf(Locale.ROOT, "%d,%.3f,%.3f,%.3f,%d,%d,%.6f%n", count,
                    nanos[rounds / 2] / (double) iterations, nanos[0] / (double) iterations,
                    nanos[rounds - 1] / (double) iterations, bytes[0], bytes[rounds - 1],
                    allocation == null ? -1.0 : bytes[rounds / 2] / (double) iterations);
        }
    }

    private static void dispatch(EventSource<Tick> source, Tick tick, int count) {
        for (int i = 0; i < count; i++) source.emit(tick);
    }

    private static ThreadMXBean allocationMeter() {
        java.lang.management.ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        if (!(bean instanceof ThreadMXBean hotspot) || !hotspot.isThreadAllocatedMemorySupported()) return null;
        if (!hotspot.isThreadAllocatedMemoryEnabled()) hotspot.setThreadAllocatedMemoryEnabled(true);
        return hotspot;
    }
}
