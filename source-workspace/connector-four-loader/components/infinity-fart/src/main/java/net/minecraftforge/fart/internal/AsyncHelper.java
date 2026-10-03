/*
 * Copyright (c) Forge Development LLC and contributors
 * SPDX-License-Identifier: LGPL-2.1-only
 * Modified 2026-10-03 for Unified Infinity: direct single-worker mode with
 * interruption preservation and no nested executor or per-entry futures.
 */

package net.minecraftforge.fart.internal;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.stream.Collectors;

class AsyncHelper {
    private final ExecutorService exec;
    AsyncHelper(int threads) {
        if (threads <= 0)
            throw new IllegalArgumentException("Really.. no threads to process things? What do you want me to use a genie?");
        else if (threads == 1)
            exec = null; // Unified Infinity: caller-thread execution, owned by the outer JAR budget.
        else
            exec = Executors.newWorkStealingPool(threads);
    }

    public <I> void consumeAll(Collection<? extends I> inputs, Function<I, String> namer, Consumer<I> consumer) {
        if (exec == null) {
            for (I input : inputs) {
                runDirect(namer.apply(input), () -> { consumer.accept(input); return null; });
            }
            return;
        }
        Function<I, Pair<String, Callable<Void>>> toCallable = i -> new Pair<>(namer.apply(i), () -> {
            consumer.accept(i);
            return null;
        });
        invokeAll(inputs.stream().map(toCallable).collect(Collectors.toList()));
    }

    public <I,O> List<O> invokeAll(Collection<? extends I> inputs, Function<I, String> namer, Function<I, O> converter) {
        if (exec == null) {
            List<O> results = new ArrayList<>(inputs.size());
            for (I input : inputs) {
                O result = runDirect(namer.apply(input), () -> converter.apply(input));
                if (result != null) results.add(result);
            }
            return results;
        }
        Function<I, Pair<String, Callable<O>>> toCallable = i -> new Pair<>(namer.apply(i), () -> converter.apply(i));
        return invokeAll(inputs.stream().map(toCallable).collect(Collectors.toList()));
    }

    public <O> List<O> invokeAll(Collection<Pair<String, ? extends Callable<O>>> tasks) {
        if (exec == null) {
            List<O> results = new ArrayList<>(tasks.size());
            for (Pair<String, ? extends Callable<O>> task : tasks) {
                O result = runDirect(task.getLeft(), task.getRight());
                if (result != null) results.add(result);
            }
            return results;
        }
            List<O> ret = new ArrayList<>(tasks.size());
            List<Pair<String, Future<O>>> processed = new ArrayList<>(tasks.size());
            for (Pair<String, ? extends Callable<O>> task : tasks) {
                processed.add(new Pair<>(task.getLeft(), exec.submit(task.getRight())));
            }
            for (Pair<String, Future<O>> future : processed) {
                try {
                    O done = future.getRight().get();
                    if (done != null)
                        ret.add(done);
                } catch (InterruptedException | ExecutionException e) {
                    throw new RuntimeException("Failed to execute task " + future.getLeft(), e);
                }
            }
            return ret;
    }

    private static <O> O runDirect(String name, Callable<O> operation) {
        try {
            if (Thread.currentThread().isInterrupted()) throw new InterruptedException("Entry batch cancelled");
            return operation.call();
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("Failed to execute task " + name, interrupted);
        } catch (Throwable failure) {
            // Match the asynchronous branch's named failure + ExecutionException cause chain.
            throw new RuntimeException("Failed to execute task " + name, new ExecutionException(failure));
        }
    }

    public void shutdown() {
        if (exec != null) exec.shutdown();
    }
}
