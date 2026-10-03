package org.sinytra.connector.infinity;

import java.io.IOException;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

/** Native-free caller ownership, progress, cancellation, and failure-drain regression tests. */
final class CooperativePumpTest {
    static void run() throws Exception {
        successfulWaitPumpsOnCaller();
        closeCancellationPumpsUntilWorkersDrain();
        originalFailureSurvivesDrainPumpFailure();
        pumpedTimeoutRetainsDeadline();
    }

    private static void successfulWaitPumpsOnCaller() throws Exception {
        Thread owner = Thread.currentThread();
        CountDownLatch started = new CountDownLatch(1), release = new CountDownLatch(1);
        AtomicInteger ticks = new AtomicInteger();
        List<Integer> output = BoundedBatch.map(List.of(4, 2, 1), 2, Duration.ofSeconds(5), value -> {
            if (value == 4) { started.countDown(); check(release.await(3, TimeUnit.SECONDS), "pump did not release waiting work"); }
            return value * 2;
        }, () -> {
            check(Thread.currentThread() == owner, "pump left calling thread");
            if (started.getCount() == 0 && ticks.incrementAndGet() >= 3) release.countDown();
        });
        check(output.equals(List.of(8, 4, 2)), "pumping changed input-order outputs");
        check(ticks.get() >= 3, "blocked future did not keep pumping");
    }

    private static void closeCancellationPumpsUntilWorkersDrain() throws Exception {
        Thread owner = Thread.currentThread();
        RuntimeException close = new IllegalStateException("test close request");
        AtomicBoolean started = new AtomicBoolean(), interrupted = new AtomicBoolean(), cancelled = new AtomicBoolean();
        AtomicInteger active = new AtomicInteger(), drainTicks = new AtomicInteger();
        CountDownLatch release = new CountDownLatch(1);
        try {
            BoundedBatch.map(List.of(1), 1, Duration.ofSeconds(5), value -> {
                active.incrementAndGet(); started.set(true);
                try {
                    try { release.await(3, TimeUnit.SECONDS); }
                    catch (InterruptedException expected) {
                        interrupted.set(true);
                        check(awaitDrainRelease(release), "drain stopped pumping after cancel");
                    }
                    return value;
                } finally { active.decrementAndGet(); }
            }, () -> {
                check(Thread.currentThread() == owner, "cancel/drain pump left owner");
                if (started.get() && cancelled.compareAndSet(false, true)) throw close;
                if (interrupted.get() && drainTicks.incrementAndGet() >= 3) release.countDown();
            });
            throw new AssertionError("close cancellation swallowed");
        } catch (RuntimeException expected) { check(expected == close, "original close exception replaced"); }
        finally { release.countDown(); }
        check(interrupted.get() && drainTicks.get() >= 3, "cancellation was not pumped through worker drain");
        check(active.get() == 0, "resources could close before cancelled worker drained");
    }

    private static void originalFailureSurvivesDrainPumpFailure() throws Exception {
        AtomicBoolean interrupted = new AtomicBoolean();
        CountDownLatch started = new CountDownLatch(2), release = new CountDownLatch(1);
        CountDownLatch waitingInsideCancellationHandler = new CountDownLatch(1);
        RuntimeException pumpFailure = new IllegalStateException("test drain pump error");
        try {
            BoundedBatch.map(List.of(0, 1), 2, Duration.ofSeconds(5), value -> {
                started.countDown(); check(started.await(3, TimeUnit.SECONDS), "failure work did not overlap");
                if (value == 0) {
                    check(waitingInsideCancellationHandler.await(3, TimeUnit.SECONDS), "second worker did not enter its cancellable wait");
                    throw new IOException("original transform failure");
                }
                try {
                    // Signal only inside the catch scope; cancellation before this point
                    // otherwise interrupts the overlap barrier instead of the drain fixture.
                    waitingInsideCancellationHandler.countDown();
                    release.await(3, TimeUnit.SECONDS);
                }
                catch (InterruptedException expected) {
                    interrupted.set(true);
                    check(awaitDrainRelease(release), "failed batch did not drain");
                }
                return value;
            }, () -> {
                if (interrupted.get()) { release.countDown(); throw pumpFailure; }
            });
            throw new AssertionError("transform failure swallowed");
        } catch (BoundedBatch.BatchException expected) {
            check(expected.inputIndex() == 0 && expected.getCause() instanceof IOException, "transform cause/attribution replaced");
            check(java.util.Arrays.asList(expected.getSuppressed()).contains(pumpFailure), "drain pump failure lost");
        } finally { release.countDown(); }
    }

    private static void pumpedTimeoutRetainsDeadline() throws Exception {
        AtomicInteger ticks = new AtomicInteger(), active = new AtomicInteger();
        try {
            BoundedBatch.map(List.of(1), 1, Duration.ofMillis(100), value -> {
                active.incrementAndGet();
                try { Thread.sleep(30_000); return value; }
                finally { active.decrementAndGet(); }
            }, ticks::incrementAndGet);
            throw new AssertionError("pump extended batch timeout");
        } catch (java.util.concurrent.TimeoutException expected) { }
        check(ticks.get() >= 2 && active.get() == 0, "timeout did not pump/drain");
    }

    /** Future.cancel(true) and shutdownNow may both interrupt the same worker.
     * Keep the drain fixture alive until the caller actually pumps its release;
     * a second interrupt must not accidentally bypass the behavior under test. */
    private static boolean awaitDrainRelease(CountDownLatch release) {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);
        boolean interruptedAgain = false;
        try {
            while (true) {
                long remaining = deadline - System.nanoTime();
                if (remaining <= 0) return release.getCount() == 0;
                try { return release.await(remaining, TimeUnit.NANOSECONDS); }
                catch (InterruptedException repeated) { interruptedAgain = true; }
            }
        } finally {
            if (interruptedAgain) Thread.currentThread().interrupt();
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
