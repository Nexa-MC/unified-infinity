package net.minecraftforge.fart.internal;

import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.sinytra.connector.infinity.BoundedBatch;
import java.time.Duration;

/** Package-level tests of the compiled real FART source patch, not a surrogate. */
public final class DirectEntryTest {
    public static void main(String[] args) throws Exception {
        Thread owner = Thread.currentThread();
        AsyncHelper helper = new AsyncHelper(1);
        List<Integer> results = helper.invokeAll(List.of(1, 2, 3), Object::toString, i -> {
            check(Thread.currentThread() == owner, "entry escaped caller thread");
            return i == 2 ? null : i * 2;
        });
        check(results.equals(List.of(2, 6)), "order or null-filter contract changed");
        AtomicInteger consumed = new AtomicInteger();
        helper.consumeAll(List.of(1, 2, 3), Object::toString, i -> {
            check(Thread.currentThread() == owner, "consumer escaped owner thread");
            consumed.addAndGet(i);
        });
        check(consumed.get() == 6, "consumer incomplete");
        List<Pair<String, ? extends Callable<Integer>>> calls = List.of(new Pair<>("one", () -> 1), new Pair<>("two", () -> 2));
        check(helper.invokeAll(calls).equals(List.of(1, 2)), "callable overload order");
        try {
            helper.invokeAll(List.of(1), Object::toString, i -> { throw new IllegalArgumentException("intentional"); });
            throw new AssertionError("entry exception swallowed");
        } catch (RuntimeException expected) {
            check(expected.getCause() instanceof java.util.concurrent.ExecutionException, "upstream cause shape lost");
            check(expected.getCause().getCause() instanceof IllegalArgumentException, "entry cause lost");
        }
        helper.shutdown();

        CountDownLatch active = new CountDownLatch(1);
        AtomicReference<Throwable> failure = new AtomicReference<>();
        AtomicInteger processing = new AtomicInteger();
        Thread caller = new Thread(() -> {
            try {
                BoundedBatch.map(List.of(1, 2, 3), 2, Duration.ofSeconds(20), i -> {
                    AsyncHelper entries = new AsyncHelper(1);
                    try {
                        return entries.invokeAll(List.of("entry"), s -> s, entry -> {
                            check(Thread.currentThread().getName().startsWith("infinity-jar-transform-"), "nested async worker created");
                            processing.incrementAndGet();
                            try {
                                active.countDown();
                                Thread.sleep(30_000);
                            } catch (InterruptedException interrupted) {
                                Thread.currentThread().interrupt();
                                throw new RuntimeException(interrupted);
                            } finally { processing.decrementAndGet(); }
                            return entry;
                        });
                    } finally { entries.shutdown(); }
                });
                failure.set(new AssertionError("interruption swallowed"));
            } catch (InterruptedException expected) {
                check(Thread.currentThread().isInterrupted(), "caller interruption not preserved");
                if (processing.get() != 0) failure.set(new AssertionError("inner entry alive after batch return"));
            } catch (Throwable unexpected) { failure.set(unexpected); }
        });
        caller.start();
        check(active.await(3, TimeUnit.SECONDS), "entry never started");
        caller.interrupt();
        caller.join(5_000);
        check(!caller.isAlive() && failure.get() == null, "cancel/drain: " + failure.get());
        check(processing.get() == 0, "orphan entry work");
        Thread.currentThread().interrupt();
        try {
            new AsyncHelper(1).invokeAll(List.of(1), Object::toString, i -> { throw new AssertionError("cancelled task ran"); });
            throw new AssertionError("pre-existing interruption ignored");
        } catch (RuntimeException expected) {
            check(Thread.currentThread().isInterrupted(), "entry interruption consumed");
        } finally { Thread.interrupted(); }
        System.out.println("PASS direct FART entry ownership, ordering, failure, and cancellation tests");
    }

    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
