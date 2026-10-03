package org.sinytra.connector.infinity;

import java.time.Duration;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

/** Bounded submission window, input-order results and input-order exception attribution. */
public final class BoundedBatch {
    private static final long PUMP_SLICE_NANOS = TimeUnit.MILLISECONDS.toNanos(16);
    private BoundedBatch() {}

    @FunctionalInterface
    public interface Operation<I, O> {
        O apply(I input) throws Exception;
    }

    public static final class BatchException extends Exception {
        private final int inputIndex;
        BatchException(int inputIndex, Throwable cause) {
            super("Transform batch failed at input index " + inputIndex, cause);
            this.inputIndex = inputIndex;
        }
        public int inputIndex() { return this.inputIndex; }
    }

    public static <I, O> List<O> map(List<I> inputs, int workers, Duration timeout, Operation<I, O> operation)
        throws InterruptedException, BatchException, TimeoutException {
        return map(inputs, workers, timeout, operation, () -> { });
    }

    /** The pump runs only on the calling thread; transform workers never access the window. */
    public static <I, O> List<O> map(List<I> inputs, int workers, Duration timeout, Operation<I, O> operation, Runnable callerPump)
        throws InterruptedException, BatchException, TimeoutException {
        java.util.Objects.requireNonNull(callerPump, "callerPump");
        if (inputs.isEmpty()) return List.of();
        if (workers < 1 || timeout.isNegative() || timeout.isZero()) throw new IllegalArgumentException("Invalid batch policy");
        int width = Math.min(inputs.size(), workers);
        AtomicInteger serial = new AtomicInteger();
        ConcurrentLinkedQueue<Thread> ownedThreads = new ConcurrentLinkedQueue<>();
        ThreadPoolExecutor executor = new ThreadPoolExecutor(width, width, 0L, TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<>(width), runnable -> {
                Thread thread = new Thread(runnable, "infinity-jar-transform-" + serial.incrementAndGet());
                thread.setDaemon(false);
                ownedThreads.add(thread);
                return thread;
            }, new ThreadPoolExecutor.AbortPolicy());
        ArrayDeque<Future<O>> window = new ArrayDeque<>(width);
        List<O> outputs = new ArrayList<>(inputs.size());
        long deadline = System.nanoTime() + timeout.toNanos();
        boolean succeeded = false;
        boolean interrupted = false;
        Throwable pendingFailure = null;
        try {
            int submitted = 0;
            while (submitted < width) {
                I input = inputs.get(submitted++);
                window.addLast(executor.submit(() -> operation.apply(input)));
            }
            for (int index = 0; index < inputs.size(); index++) {
                long remaining = deadline - System.nanoTime();
                if (remaining <= 0) throw new TimeoutException("Timed out waiting for jar remap");
                // Do not remove this future until get succeeds: failure cleanup must cancel it too.
                try {
                    outputs.add(await(window.getFirst(), deadline, callerPump));
                } catch (ExecutionException e) {
                    throw new BatchException(index, e.getCause());
                }
                window.removeFirst();
                if (submitted < inputs.size()) {
                    I input = inputs.get(submitted++);
                    window.addLast(executor.submit(() -> operation.apply(input)));
                }
            }
            succeeded = true;
            return List.copyOf(outputs);
        } catch (InterruptedException e) {
            interrupted = true; pendingFailure = e;
            throw e;
        } catch (BatchException | TimeoutException | RuntimeException | Error failure) {
            pendingFailure = failure;
            throw failure;
        } finally {
            if (succeeded) {
                executor.shutdown();
            } else {
                window.forEach(future -> future.cancel(true));
                executor.shutdownNow();
            }
            // Never let global bytecode-loader/Mixin-cache cleanup race an active transformer.
            // Cooperative tasks terminate promptly; an uninterruptible task requires process cancellation.
            Throwable drainPumpFailure = null;
            InterruptedException drainInterrupt = null;
            // Executor TERMINATED is published inside a worker's exit bookkeeping,
            // before that actual Thread necessarily returns. Join our exact threads too.
            while (!executor.isTerminated() || ownedThreads.stream().anyMatch(Thread::isAlive)) {
                try {
                    callerPump.run();
                } catch (RuntimeException | Error failure) {
                    // Close/cancel may keep throwing on every pump. Preserve only the first new failure.
                    if (drainPumpFailure == null) drainPumpFailure = failure;
                    window.forEach(future -> future.cancel(true));
                    executor.shutdownNow();
                }
                try {
                    if (!executor.isTerminated()) {
                        executor.awaitTermination(PUMP_SLICE_NANOS, TimeUnit.NANOSECONDS);
                    } else {
                        Thread tail = ownedThreads.stream().filter(Thread::isAlive).findFirst().orElse(null);
                        if (tail != null) tail.join(TimeUnit.NANOSECONDS.toMillis(PUMP_SLICE_NANOS));
                    }
                } catch (InterruptedException e) {
                    interrupted = true;
                    if (drainInterrupt == null) drainInterrupt = e;
                    window.forEach(future -> future.cancel(true));
                    executor.shutdownNow();
                }
            }
            if (interrupted) Thread.currentThread().interrupt();
            if (drainInterrupt != null) {
                if (pendingFailure != null && pendingFailure != drainInterrupt) pendingFailure.addSuppressed(drainInterrupt);
                else if (pendingFailure == null && drainPumpFailure == null) throw drainInterrupt;
            }
            if (drainPumpFailure != null && drainPumpFailure != pendingFailure) {
                if (pendingFailure != null) pendingFailure.addSuppressed(drainPumpFailure);
                else if (drainPumpFailure instanceof RuntimeException runtime) throw runtime;
                else throw (Error) drainPumpFailure;
            }
        }
    }

    private static <O> O await(Future<O> future, long deadline, Runnable callerPump)
        throws InterruptedException, ExecutionException, TimeoutException {
        while (true) {
            if (Thread.currentThread().isInterrupted()) throw new InterruptedException("Transform batch interrupted");
            callerPump.run();
            long remaining = deadline - System.nanoTime();
            if (remaining <= 0) throw new TimeoutException("Timed out waiting for jar remap");
            try {
                return future.get(Math.min(remaining, PUMP_SLICE_NANOS), TimeUnit.NANOSECONDS);
            } catch (TimeoutException tickDue) {
                // A slice expiry means pump again, never that the transform itself failed.
            }
        }
    }
}
