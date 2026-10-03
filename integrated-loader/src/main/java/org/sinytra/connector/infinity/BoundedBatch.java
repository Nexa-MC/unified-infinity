package org.sinytra.connector.infinity;

import java.time.Duration;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

/** Bounded submission window, input-order results and input-order exception attribution. */
public final class BoundedBatch {
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
        if (inputs.isEmpty()) return List.of();
        if (workers < 1 || timeout.isNegative() || timeout.isZero()) throw new IllegalArgumentException("Invalid batch policy");
        int width = Math.min(inputs.size(), workers);
        AtomicInteger serial = new AtomicInteger();
        ThreadPoolExecutor executor = new ThreadPoolExecutor(width, width, 0L, TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<>(width), runnable -> {
                Thread thread = new Thread(runnable, "infinity-jar-transform-" + serial.incrementAndGet());
                thread.setDaemon(false);
                return thread;
            }, new ThreadPoolExecutor.AbortPolicy());
        ArrayDeque<Future<O>> window = new ArrayDeque<>(width);
        List<O> outputs = new ArrayList<>(inputs.size());
        long deadline = System.nanoTime() + timeout.toNanos();
        boolean succeeded = false;
        boolean interrupted = false;
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
                    outputs.add(window.getFirst().get(remaining, TimeUnit.NANOSECONDS));
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
            interrupted = true;
            throw e;
        } finally {
            if (succeeded) {
                executor.shutdown();
            } else {
                window.forEach(future -> future.cancel(true));
                executor.shutdownNow();
            }
            // Never let global bytecode-loader/Mixin-cache cleanup race an active transformer.
            // Cooperative tasks terminate promptly; an uninterruptible task requires process cancellation.
            while (!executor.isTerminated()) {
                try {
                    executor.awaitTermination(1, TimeUnit.DAYS);
                } catch (InterruptedException e) {
                    interrupted = true;
                    window.forEach(future -> future.cancel(true));
                    executor.shutdownNow();
                }
            }
            if (interrupted) Thread.currentThread().interrupt();
        }
    }
}
