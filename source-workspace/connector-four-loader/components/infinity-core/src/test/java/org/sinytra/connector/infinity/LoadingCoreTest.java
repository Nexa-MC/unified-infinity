package org.sinytra.connector.infinity;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import java.util.stream.IntStream;

/** No mocks of host classes: focused executable tests of the actual shared core. */
public final class LoadingCoreTest {
    private static int tests;
    public static void main(String[] args) throws Exception {
        policyBudgets();
        boundedConcurrencyAndOrderedOutputs();
        sequentialDifferential();
        deterministicFailureAndCleanup();
        interruptionAndCleanup();
        timeoutAndCleanup();
        CooperativePumpTest.run();
        tests++;
        boundedSubmissionWindow();
        progressSnapshots();
        ownedResourceScope();
        emptyBatch();
        assertNoWorkers();
        System.out.println("PASS " + tests + " loading core tests");
    }

    private static void policyBudgets() {
        check(LoadingPolicy.compute(100, 128, 8L << 30, 4, Integer.MAX_VALUE).workers() == 4, "configured cap");
        check(LoadingPolicy.compute(100, 128, 1L << 30, 4, Integer.MAX_VALUE).workers() == 2, "heap cap");
        check(LoadingPolicy.compute(100, 2, 8L << 30, 4, Integer.MAX_VALUE).workers() == 1, "CPU reserve");
        check(LoadingPolicy.compute(100, 1, 128L << 20, 4, Integer.MAX_VALUE).workers() == 1, "minimum one worker");
        check(LoadingPolicy.compute(0, 128, 8L << 30, 4, 1).workers() == 0, "empty budget");
        check(LoadingPolicy.compute(3, 128, 8L << 30, 4, Integer.MAX_VALUE).workers() == 3, "input cap");
        String old = System.getProperty(LoadingPolicy.WORKERS_PROPERTY);
        try {
            System.setProperty(LoadingPolicy.WORKERS_PROPERTY, "1");
            check(LoadingPolicy.current(100).workers() == 1, "sequential property");
            System.setProperty(LoadingPolicy.WORKERS_PROPERTY, "0");
            try { LoadingPolicy.current(2); throw new AssertionError("zero property accepted"); }
            catch (IllegalArgumentException expected) { }
        } finally { restoreProperty(LoadingPolicy.WORKERS_PROPERTY, old); }
        tests++;
    }

    private static void boundedConcurrencyAndOrderedOutputs() throws Exception {
        AtomicInteger active = new AtomicInteger();
        AtomicInteger peak = new AtomicInteger();
        CountDownLatch overlap = new CountDownLatch(3);
        List<Integer> inputs = IntStream.range(0, 30).boxed().toList();
        List<Integer> output = BoundedBatch.map(inputs, 3, Duration.ofSeconds(10), index -> {
            int now = active.incrementAndGet();
            peak.accumulateAndGet(now, Math::max);
            try {
                if (index < 3) {
                    overlap.countDown();
                    check(overlap.await(3, TimeUnit.SECONDS), "workers did not overlap");
                }
                Thread.sleep((3 - index % 3) * 2L);
                return index * index;
            } finally { active.decrementAndGet(); }
        });
        check(peak.get() == 3, "peak concurrency exactly bounded");
        check(active.get() == 0, "workers done on success");
        check(output.equals(inputs.stream().map(n -> n * n).toList()), "output input order");
        assertNoWorkers();
        tests++;
    }

    private static void sequentialDifferential() throws Exception {
        List<Integer> input = IntStream.range(0, 100).boxed().toList();
        List<String> sequential = BoundedBatch.map(input, 1, Duration.ofSeconds(10), i -> "jar-" + i + ":" + Integer.toHexString(i * 98731));
        List<String> bounded = BoundedBatch.map(input, 4, Duration.ofSeconds(10), i -> "jar-" + i + ":" + Integer.toHexString(i * 98731));
        check(sequential.equals(bounded), "sequential/bounded differential");
        tests++;
    }

    private static void deterministicFailureAndCleanup() throws Exception {
        AtomicInteger active = new AtomicInteger();
        CountDownLatch started = new CountDownLatch(3);
        try {
            BoundedBatch.map(List.of(0, 1, 2, 3, 4), 3, Duration.ofSeconds(5), i -> {
                active.incrementAndGet();
                try {
                    started.countDown();
                    check(started.await(2, TimeUnit.SECONDS), "failure workers did not start");
                    if (i == 0) { Thread.sleep(30); return i; }
                    if (i == 1) { Thread.sleep(10); throw new IOException("first input failure"); }
                    if (i == 2) throw new IllegalStateException("later input failed earlier");
                    Thread.sleep(30_000);
                    return i;
                } finally { active.decrementAndGet(); }
            });
            throw new AssertionError("failure was swallowed");
        } catch (BoundedBatch.BatchException expected) {
            check(expected.inputIndex() == 1, "failure input attribution deterministic");
            check(expected.getCause() instanceof IOException, "first input cause preserved");
        }
        check(active.get() == 0, "all failure workers drained before return");
        assertNoWorkers();
        tests++;
    }

    private static void interruptionAndCleanup() throws Exception {
        AtomicInteger active = new AtomicInteger();
        AtomicBoolean restored = new AtomicBoolean();
        AtomicReference<Throwable> error = new AtomicReference<>();
        CountDownLatch started = new CountDownLatch(2);
        Thread caller = new Thread(() -> {
            try {
                BoundedBatch.map(List.of(0, 1, 2, 3), 2, Duration.ofSeconds(30), i -> {
                    active.incrementAndGet();
                    try { started.countDown(); Thread.sleep(30_000); return i; }
                    finally { active.decrementAndGet(); }
                });
                error.set(new AssertionError("interrupt swallowed"));
            } catch (InterruptedException expected) {
                restored.set(Thread.currentThread().isInterrupted());
                if (active.get() != 0) error.set(new AssertionError("workers alive after interruption"));
            } catch (Throwable unexpected) { error.set(unexpected); }
        }, "test-caller");
        caller.start();
        check(started.await(3, TimeUnit.SECONDS), "interrupt workers started");
        caller.interrupt();
        caller.join(5_000);
        check(!caller.isAlive(), "interrupted caller terminates");
        check(error.get() == null, "interruption failed: " + error.get());
        check(restored.get(), "interrupt flag preserved");
        assertNoWorkers();
        tests++;
    }

    private static void timeoutAndCleanup() throws Exception {
        AtomicInteger active = new AtomicInteger();
        try {
            BoundedBatch.map(List.of(0, 1), 2, Duration.ofMillis(80), i -> {
                active.incrementAndGet();
                try { Thread.sleep(30_000); return i; }
                finally { active.decrementAndGet(); }
            });
            throw new AssertionError("timeout swallowed");
        } catch (java.util.concurrent.TimeoutException expected) { }
        check(active.get() == 0, "timeout workers drained");
        assertNoWorkers();
        tests++;
    }

    private static void boundedSubmissionWindow() throws Exception {
        AtomicInteger visited = new AtomicInteger();
        CountDownLatch firstEntered = new CountDownLatch(1);
        CountDownLatch releaseFirst = new CountDownLatch(1);
        AtomicReference<Throwable> error = new AtomicReference<>();
        Thread caller = new Thread(() -> {
            try {
                BoundedBatch.map(IntStream.range(0, 2000).boxed().toList(), 3, Duration.ofSeconds(10), i -> {
                    visited.incrementAndGet();
                    if (i == 0) { firstEntered.countDown(); releaseFirst.await(); }
                    return i;
                });
            } catch (Throwable unexpected) { error.set(unexpected); }
        });
        caller.start();
        try {
            check(firstEntered.await(2, TimeUnit.SECONDS), "window first input entered");
            Thread.sleep(100);
            check(visited.get() <= 3, "tasks admitted beyond bounded window");
        } finally { releaseFirst.countDown(); }
        caller.join(5_000);
        check(!caller.isAlive() && error.get() == null, "bounded window caller completed");
        check(visited.get() == 2000, "all inputs eventually visited");
        assertNoWorkers();
        tests++;
    }

    private static void progressSnapshots() throws Exception {
        Path directory = Files.createTempDirectory("infinity-progress-test-");
        Path snapshot = directory.resolve("state.json");
        String old = System.getProperty(LoadProgress.FILE_PROPERTY);
        try {
            System.setProperty(LoadProgress.FILE_PROPERTY, snapshot.toString());
            LoadProgress.begin(LoadProgress.Stage.DISCOVER);
            String initial = Files.readString(snapshot);
            check(initial.contains("\"completed\":null") && initial.contains("\"total\":null"), "unknown counts indeterminate");
            LoadProgress.finish(7);
            LoadProgress.begin(LoadProgress.Stage.RESOLVE);
            LoadProgress.finish(5);
            LoadProgress.begin(LoadProgress.Stage.TRANSFORM);
            LoadProgress.transformUnits(100, 0);
            String beforeCoalescing = Files.readString(snapshot);
            LoadProgress.transformedOne();
            LoadProgress.transformedOne();
            check(Files.readString(snapshot).equals(beforeCoalescing), "routine progress not coalesced");
            LoadProgress.transformUnits(5, 2);
            BoundedBatch.map(List.of(0, 1, 2), 3, Duration.ofSeconds(2), i -> { LoadProgress.transformedOne(); return i; });
            String transformed = Files.readString(snapshot);
            check(transformed.contains("\"completed\":5,\"total\":5"), "actual cache plus transformed counts");
            LoadProgress.finish(5);
            LoadProgress.begin(LoadProgress.Stage.COMMIT);
            LoadProgress.finish(null);
            String complete = Files.readString(snapshot);
            check(complete.contains("\"stage\":\"commit\",\"status\":\"complete\""), "commit terminal stage");
            check(complete.contains("\"completed\":null"), "unknown host-admission count never fabricated");
            LoadProgress.fail(new IOException("secret /private/mods/file.jar"));
            LoadProgress.finish(999);
            String failed = Files.readString(snapshot);
            check(failed.contains("\"status\":\"failed\"") && failed.contains("\"error\":\"IOException\""), "failure survives finish");
            check(!failed.contains("secret") && !failed.contains("file.jar"), "exception message omitted");
            try (var files = Files.list(directory)) { check(files.count() == 1, "temporary snapshots cleaned up"); }
        } finally {
            restoreProperty(LoadProgress.FILE_PROPERTY, old);
            Files.deleteIfExists(snapshot);
            Files.deleteIfExists(directory);
        }
        tests++;
    }

    private static void emptyBatch() throws Exception {
        check(BoundedBatch.map(List.of(), 0, Duration.ofSeconds(1), i -> i).isEmpty(), "empty batch");
        assertNoWorkers();
        tests++;
    }

    private static void ownedResourceScope() {
        List<Integer> closed = new ArrayList<>();
        ResourceScope scope = new ResourceScope();
        scope.own(() -> { closed.add(1); throw new IOException("first owned resource"); });
        scope.own(() -> { closed.add(2); throw new IOException("last owned resource"); });
        scope.own(() -> closed.add(3));
        try {
            scope.close();
            throw new AssertionError("close failure swallowed");
        } catch (RuntimeException expected) {
            check(expected.getCause() instanceof IOException, "resource close cause lost");
            check(expected.getSuppressed().length == 1, "later close failure not suppressed");
        }
        check(closed.equals(List.of(3, 2, 1)), "resources not closed in LIFO order");
        scope.close();
        check(closed.size() == 3, "resource closed twice");
        tests++;
    }

    private static void assertNoWorkers() {
        check(Thread.getAllStackTraces().keySet().stream().noneMatch(t -> t.isAlive() && t.getName().startsWith("infinity-jar-transform-")), "transform worker leaked");
    }

    private static void restoreProperty(String key, String old) {
        if (old == null) System.clearProperty(key); else System.setProperty(key, old);
    }

    private static void check(boolean result, String message) {
        if (!result) throw new AssertionError(message);
    }
}
