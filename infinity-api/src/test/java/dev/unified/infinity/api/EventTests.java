package dev.unified.infinity.api;

import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Consumer;

/** No test framework or game bootstrap required. Run with assertions enabled. */
public final class EventTests {
    private static final Capability TICK = new Capability("infinity:server_tick");
    private static int passed;

    public static void main(String[] args) throws Exception {
        run("empty dispatch", EventTests::emptyDispatch);
        run("typed payload and supertype listener", EventTests::typedPayload);
        run("insertion order across mods", EventTests::insertionOrder);
        run("duplicate registrations are independent", EventTests::duplicates);
        run("individual unsubscribe is idempotent", EventTests::unsubscribe);
        run("scope close removes only owned listeners", EventTests::scopeClose);
        run("closed handles release strong references", EventTests::closedHandleReferences);
        run("missing capability is contextual", EventTests::missingCapability);
        run("closed scope rejects registration", EventTests::closedScope);
        run("null and identifier validation", EventTests::invalidInputs);
        run("self unsubscribe does not corrupt snapshot", EventTests::selfUnsubscribe);
        run("add/remove during dispatch uses stable snapshot", EventTests::snapshotMutation);
        run("scope close during dispatch uses stable snapshot", EventTests::closeDuringDispatch);
        run("reentrant dispatch is depth-first", EventTests::reentrant);
        run("reentrant dispatch sees latest snapshot", EventTests::reentrantMutation);
        run("runtime exception fails fast with context", EventTests::listenerFailure);
        run("Error propagates unchanged", EventTests::fatalError);
        run("foreign-thread dispatch fails before callback", EventTests::wrongThread);
        run("parallel registration preserves per-thread order", EventTests::parallelRegistration);
        run("registration racing scope close has no survivors", EventTests::registerCloseRace);
        run("parallel unsubscribe and scope close are safe", EventTests::parallelClose);
        run("slow callback serializes dispatch; mutation stays nonblocking", EventTests::slowListener);
        System.out.println("PASS " + passed + " tests");
    }

    private static EventSource<Integer> source() {
        return EventSource.onCurrentThread("infinity:test_tick", TICK);
    }

    private static ModScope scope(String id) { return ModScope.open(id, Set.of(TICK)); }

    private static void emptyDispatch() {
        EventSource<Integer> source = source();
        source.emit(1);
        equal(0, source.event().listenerCount());
    }

    private static void typedPayload() {
        EventSource<String> source = EventSource.onCurrentThread("test:text", TICK);
        List<CharSequence> seen = new ArrayList<>();
        try (ModScope scope = scope("typed")) {
            Consumer<CharSequence> listener = seen::add;
            source.event().listen(scope, listener);
            source.emit("typed");
            equal(List.of("typed"), seen);
        }
    }

    private static void insertionOrder() {
        EventSource<Integer> source = source();
        List<String> seen = new ArrayList<>();
        try (ModScope first = scope("first"); ModScope second = scope("second")) {
            source.event().listen(first, value -> seen.add("a" + value));
            source.event().listen(second, value -> seen.add("b" + value));
            source.event().listen(first, value -> seen.add("c" + value));
            source.emit(3);
            equal(List.of("a3", "b3", "c3"), seen);
        }
    }

    private static void duplicates() {
        EventSource<Integer> source = source();
        AtomicInteger calls = new AtomicInteger();
        try (ModScope scope = scope("duplicates")) {
            Consumer<Integer> listener = value -> calls.incrementAndGet();
            Subscription first = source.event().listen(scope, listener);
            Subscription second = source.event().listen(scope, listener);
            first.close();
            source.emit(1);
            equal(1, calls.get());
            check(!second.isClosed(), "closing one duplicate must not close another");
        }
    }

    private static void unsubscribe() {
        EventSource<Integer> source = source();
        try (ModScope scope = scope("unsubscribe")) {
            Subscription subscription = source.event().listen(scope, value -> fail("unsubscribed callback"));
            equal(1, scope.subscriptionCount());
            subscription.close();
            subscription.close();
            check(subscription.isClosed(), "closed subscription");
            equal(0, scope.subscriptionCount());
            equal(0, source.event().listenerCount());
            source.emit(1);
        }
    }

    private static void scopeClose() {
        EventSource<Integer> firstEvent = source();
        EventSource<Integer> secondEvent = source();
        List<String> seen = new ArrayList<>();
        ModScope first = scope("first");
        try (ModScope second = scope("second")) {
            Subscription firstHandle = firstEvent.event().listen(first, value -> fail("closed owner"));
            Subscription secondHandle = secondEvent.event().listen(first, value -> fail("closed owner"));
            firstEvent.event().listen(second, value -> seen.add("survivor"));
            first.close();
            first.close();
            check(first.isClosed(), "scope closed");
            check(firstHandle.isClosed() && secondHandle.isClosed(), "all owned handles closed");
            equal(0, first.subscriptionCount());
            firstEvent.emit(1);
            secondEvent.emit(1);
            equal(List.of("survivor"), seen);
        } finally {
            first.close();
        }
    }

    private static void closedHandleReferences() throws Exception {
        EventSource<Integer> source = source();
        ModScope scope = scope("references");
        Subscription subscription = source.event().listen(scope, value -> { });
        scope.close();
        // Structural test only: production dispatch and registration use no reflection.
        for (Field field : subscription.getClass().getDeclaredFields()) {
            field.setAccessible(true);
            equal(null, field.get(subscription));
        }
    }

    private static void missingCapability() {
        EventSource<Integer> source = source();
        try (ModScope scope = ModScope.open("no_tick", Set.of())) {
            CapabilityException error = expect(CapabilityException.class,
                    () -> source.event().listen(scope, value -> { }));
            contains(error.getMessage(), "no_tick");
            contains(error.getMessage(), "infinity:test_tick");
            contains(error.getMessage(), "infinity:server_tick");
            equal(0, source.event().listenerCount());
            equal(0, scope.subscriptionCount());
        }
    }

    private static void closedScope() {
        ModScope scope = scope("closed_mod");
        scope.close();
        IllegalStateException error = expect(IllegalStateException.class,
                () -> source().event().listen(scope, value -> { }));
        contains(error.getMessage(), "closed_mod");
        contains(error.getMessage(), "closed");
    }

    private static void invalidInputs() {
        expect(IllegalArgumentException.class, () -> new Capability("no namespace"));
        expect(IllegalArgumentException.class, () -> EventSource.onCurrentThread("bad", TICK));
        expect(IllegalArgumentException.class, () -> scope("bad mod"));
        expect(NullPointerException.class, () -> new Capability(null));
        expect(NullPointerException.class, () -> EventSource.onCurrentThread("test:ok", null));
        EventSource<Integer> source = source();
        expect(NullPointerException.class, () -> source.emit(null));
        expect(NullPointerException.class, () -> source.event().listen(null, value -> { }));
        try (ModScope scope = scope("valid")) {
            expect(NullPointerException.class, () -> source.event().listen(scope, null));
        }
    }

    private static void selfUnsubscribe() {
        EventSource<Integer> source = source();
        AtomicReference<Subscription> self = new AtomicReference<>();
        List<String> seen = new ArrayList<>();
        try (ModScope scope = scope("self")) {
            self.set(source.event().listen(scope, value -> { seen.add("self"); self.get().close(); }));
            source.event().listen(scope, value -> seen.add("other"));
            source.emit(1);
            source.emit(2);
            equal(List.of("self", "other", "other"), seen);
        }
    }

    private static void snapshotMutation() {
        EventSource<Integer> source = source();
        List<String> seen = new ArrayList<>();
        AtomicReference<Subscription> removed = new AtomicReference<>();
        try (ModScope scope = scope("mutator")) {
            source.event().listen(scope, value -> {
                seen.add("a" + value);
                if (value == 1) {
                    removed.get().close();
                    source.event().listen(scope, inner -> seen.add("c" + inner));
                }
            });
            removed.set(source.event().listen(scope, value -> seen.add("b" + value)));
            source.emit(1);
            source.emit(2);
            equal(List.of("a1", "b1", "a2", "c2"), seen);
        }
    }

    private static void closeDuringDispatch() {
        EventSource<Integer> source = source();
        List<String> seen = new ArrayList<>();
        ModScope scope = scope("closing");
        source.event().listen(scope, value -> { seen.add("a"); scope.close(); });
        source.event().listen(scope, value -> seen.add("b"));
        source.emit(1);
        source.emit(2);
        equal(List.of("a", "b"), seen);
        equal(0, source.event().listenerCount());
    }

    private static void reentrant() {
        EventSource<Integer> source = source();
        List<String> seen = new ArrayList<>();
        try (ModScope scope = scope("nested")) {
            source.event().listen(scope, value -> {
                seen.add("a" + value);
                if (value == 1) source.emit(2);
            });
            source.event().listen(scope, value -> seen.add("b" + value));
            source.emit(1);
            equal(List.of("a1", "a2", "b2", "b1"), seen);
        }
    }

    private static void reentrantMutation() {
        EventSource<Integer> source = source();
        List<String> seen = new ArrayList<>();
        AtomicReference<Subscription> removed = new AtomicReference<>();
        try (ModScope scope = scope("nested_mutator")) {
            source.event().listen(scope, value -> {
                seen.add("a" + value);
                if (value == 1) {
                    removed.get().close();
                    source.event().listen(scope, inner -> seen.add("c" + inner));
                    source.emit(2);
                }
            });
            removed.set(source.event().listen(scope, value -> seen.add("b" + value)));
            source.emit(1);
            equal(List.of("a1", "a2", "c2", "b1"), seen);
        }
    }

    private static void listenerFailure() {
        EventSource<Integer> source = source();
        List<String> seen = new ArrayList<>();
        RuntimeException cause = new IllegalArgumentException("broken listener");
        try (ModScope before = scope("before"); ModScope broken = scope("broken"); ModScope after = scope("after")) {
            source.event().listen(before, value -> seen.add("before"));
            source.event().listen(broken, value -> { throw cause; });
            source.event().listen(after, value -> seen.add("after"));
            EventDispatchException error = expect(EventDispatchException.class, () -> source.emit(1));
            equal("infinity:test_tick", error.eventId());
            equal("broken", error.modId());
            equal(1, error.listenerIndex());
            check(error.getCause() == cause, "original cause preserved");
            equal(List.of("before"), seen);
            broken.close();
            source.emit(2);
            equal(List.of("before", "before", "after"), seen);
        }
    }

    private static void fatalError() {
        EventSource<Integer> source = source();
        AssertionError fatal = new AssertionError("fatal");
        try (ModScope scope = scope("fatal")) {
            source.event().listen(scope, value -> { throw fatal; });
            source.event().listen(scope, value -> fail("must not continue after Error"));
            check(expect(AssertionError.class, () -> source.emit(1)) == fatal, "Error identity preserved");
        }
    }

    private static void wrongThread() throws Exception {
        EventSource<Integer> source = source();
        AtomicInteger calls = new AtomicInteger();
        AtomicReference<Throwable> failure = new AtomicReference<>();
        try (ModScope scope = scope("thread")) {
            source.event().listen(scope, value -> calls.incrementAndGet());
            Thread worker = worker("wrong-dispatch-thread", failure, () -> {
                IllegalStateException error = expect(IllegalStateException.class, () -> source.emit(1));
                contains(error.getMessage(), "wrong-dispatch-thread");
                contains(error.getMessage(), "infinity:test_tick");
            });
            join(worker, failure);
            equal(0, calls.get());
            source.emit(1);
            equal(1, calls.get());
        }
    }

    private static void parallelRegistration() throws Exception {
        EventSource<Integer> source = source();
        AtomicReference<Throwable> failure = new AtomicReference<>();
        List<Integer> seen = new ArrayList<>();
        List<ModScope> scopes = new ArrayList<>();
        try {
            List<Thread> workers = new ArrayList<>();
            for (int thread = 0; thread < 4; thread++) {
                int group = thread;
                ModScope scope = scope("parallel_mod_" + group);
                scopes.add(scope);
                workers.add(worker("register-" + group, failure, () -> {
                    for (int index = 0; index < 200; index++) {
                        int token = group * 1000 + index;
                        source.event().listen(scope, ignored -> seen.add(token));
                    }
                }));
            }
            for (Thread worker : workers) join(worker, failure);
            equal(800, source.event().listenerCount());
            source.emit(1);
            int[] next = new int[4];
            for (int token : seen) equal(next[token / 1000]++, token % 1000);
            for (int count : next) equal(200, count);
        } finally {
            scopes.forEach(ModScope::close);
        }
        equal(0, source.event().listenerCount());
    }

    private static void registerCloseRace() throws Exception {
        for (int round = 0; round < 30; round++) {
            EventSource<Integer> source = source();
            ModScope scope = scope("race");
            AtomicReference<Throwable> failure = new AtomicReference<>();
            CountDownLatch start = new CountDownLatch(1);
            Thread register = worker("race-register", failure, () -> {
                await(start);
                for (int i = 0; i < 100; i++) {
                    try {
                        source.event().listen(scope, value -> { });
                    } catch (IllegalStateException closed) {
                        check(scope.isClosed(), "only closed scope may reject registration");
                        return;
                    }
                }
            });
            Thread close = worker("race-close", failure, () -> { await(start); scope.close(); });
            start.countDown();
            join(register, failure);
            join(close, failure);
            equal(0, scope.subscriptionCount());
            equal(0, source.event().listenerCount());
        }
    }

    private static void parallelClose() throws Exception {
        EventSource<Integer> source = source();
        ModScope scope = scope("parallel_close");
        List<Subscription> subscriptions = new ArrayList<>();
        for (int i = 0; i < 300; i++) subscriptions.add(source.event().listen(scope, value -> { }));
        AtomicReference<Throwable> failure = new AtomicReference<>();
        Thread first = worker("individual-close", failure, () -> subscriptions.forEach(Subscription::close));
        Thread second = worker("scope-close", failure, scope::close);
        join(first, failure);
        join(second, failure);
        equal(0, source.event().listenerCount());
        equal(0, scope.subscriptionCount());
        for (Subscription subscription : subscriptions) check(subscription.isClosed(), "every handle closed");
    }

    private static void slowListener() throws Exception {
        EventSource<Integer> source = source();
        List<String> seen = new ArrayList<>();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch changed = new CountDownLatch(1);
        AtomicReference<Throwable> failure = new AtomicReference<>();
        try (ModScope slow = scope("slow"); ModScope removed = scope("removed"); ModScope added = scope("added")) {
            source.event().listen(slow, value -> {
                seen.add("slow-start");
                entered.countDown();
                await(changed);
                seen.add("slow-end");
            });
            source.event().listen(removed, value -> seen.add("removed"));
            Thread worker = worker("concurrent-mod", failure, () -> {
                try {
                    await(entered);
                    expect(IllegalStateException.class, () -> source.emit(99));
                    removed.close();
                    source.event().listen(added, value -> seen.add("added"));
                    equal(2, source.event().listenerCount());
                } finally {
                    changed.countDown();
                }
            });
            source.emit(1);
            join(worker, failure);
            equal(List.of("slow-start", "slow-end", "removed"), seen);
            seen.clear();
            source.emit(2);
            equal(List.of("slow-start", "slow-end", "added"), seen);
        }
    }

    private static Thread worker(String name, AtomicReference<Throwable> failure, CheckedRunnable task) {
        Thread thread = new Thread(() -> {
            try { task.run(); } catch (Throwable error) { failure.compareAndSet(null, error); }
        }, name);
        thread.setDaemon(true);
        thread.start();
        return thread;
    }

    private static void join(Thread worker, AtomicReference<Throwable> failure) throws Exception {
        worker.join(TimeUnit.SECONDS.toMillis(10));
        check(!worker.isAlive(), "worker did not finish: " + worker.getName());
        if (failure.get() != null) throw new AssertionError("worker failed", failure.get());
    }

    private static void await(CountDownLatch latch) {
        try {
            check(latch.await(10, TimeUnit.SECONDS), "latch timed out");
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new AssertionError(interrupted);
        }
    }

    private static void run(String name, CheckedRunnable test) throws Exception {
        test.run();
        passed++;
        System.out.println("PASS " + name);
    }

    private static void contains(String actual, String expected) { check(actual.contains(expected), actual); }
    private static void equal(Object expected, Object actual) {
        check(java.util.Objects.equals(expected, actual), "expected " + expected + ", got " + actual);
    }
    private static void check(boolean condition, String message) { if (!condition) fail(message); }
    private static void fail(String message) { throw new AssertionError(message); }

    private static <T extends Throwable> T expect(Class<T> type, CheckedRunnable task) {
        try { task.run(); } catch (Throwable failure) {
            if (type.isInstance(failure)) return type.cast(failure);
            throw new AssertionError("Expected " + type.getName() + ", got " + failure, failure);
        }
        throw new AssertionError("Expected " + type.getName());
    }

    @FunctionalInterface
    private interface CheckedRunnable { void run() throws Exception; }
}
