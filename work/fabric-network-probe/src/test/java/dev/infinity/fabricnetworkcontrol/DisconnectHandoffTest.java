// SPDX-License-Identifier: MIT
package dev.infinity.fabricnetworkcontrol;

import java.util.ArrayDeque;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/** Actual production handoff, real Java threads, opaque identity/queue/tick fixtures.
 * Does not launch Minecraft, invoke its queue, or exercise live PLAY dispatch.
 */
public final class DisconnectHandoffTest {
    private static int checked;
    private DisconnectHandoffTest() {}

    static void run() {
        Object client = new Object(), handler = new Object(), connection = new Object();
        var offThread = new DisconnectHandoff();
        check(offThread.poll() == null);
        offThread.beginTeardown(client, handler, connection);
        check(offThread.isTearingDown());
        worker(() -> offThread.observe(client, handler, connection));
        check(offThread.poll() == null); // A callback cannot consume during explicit teardown.
        offThread.finishTeardown();
        check(!offThread.isTearingDown());
        check(offThread.poll() == connection);
        worker(() -> offThread.observe(client, handler, connection));
        offThread.observe(client, handler, connection);
        check(offThread.poll() == connection); // Netty + owner duplicate is idempotent.
        reject(() -> offThread.beginTeardown(client, handler, connection), "client_disconnect_mismatch");

        var ownerThread = new DisconnectHandoff();
        ownerThread.beginTeardown(client, handler, connection);
        ownerThread.observe(client, handler, connection);
        check(ownerThread.poll() == null);
        ownerThread.finishTeardown();
        check(ownerThread.poll() == connection);

        var absent = new DisconnectHandoff();
        absent.beginTeardown(client, handler, connection);
        absent.finishTeardown();
        check(absent.poll() == null); // Closing without the API callback cannot qualify.

        for (boolean workerNotice : new boolean[] { false, true }) {
            var early = new DisconnectHandoff();
            Runnable observation = () -> early.observe(client, handler, connection);
            if (workerNotice) worker(observation); else observation.run();
            reject(early::poll, "client_early_disconnect");
            reject(() -> early.beginTeardown(client, handler, connection), "client_early_disconnect");
            early.observe(client, handler, connection);
            reject(early::poll, "client_early_disconnect");
        }
        var malformedEarly = new DisconnectHandoff();
        worker(() -> malformedEarly.observe(null, null, null));
        reject(malformedEarly::poll, "client_early_disconnect");

        Object[][] mismatches = {
            { new Object(), handler, connection }, { client, new Object(), connection },
            { client, handler, new Object() }, { null, handler, connection },
            { client, null, connection }, { client, handler, null }
        };
        for (Object[] mismatch : mismatches) {
            var conflict = new DisconnectHandoff();
            conflict.beginTeardown(client, handler, connection);
            conflict.observe(client, handler, connection);
            worker(() -> conflict.observe(mismatch[0], mismatch[1], mismatch[2]));
            conflict.observe(client, handler, connection); // A good duplicate cannot erase failure.
            check(conflict.poll() == null);
            conflict.finishTeardown();
            reject(conflict::poll, "client_disconnect_mismatch");
            reject(conflict::poll, "client_disconnect_mismatch");
        }
        for (Object[] missing : new Object[][] {
                { null, handler, connection }, { client, null, connection }, { client, handler, null } }) {
            var invalidArm = new DisconnectHandoff();
            reject(() -> invalidArm.beginTeardown(missing[0], missing[1], missing[2]), "client_disconnect_mismatch");
        }
        Object equal1 = new EqualIdentity(), equal2 = new EqualIdentity();
        check(equal1.equals(equal2));
        var identity = new DisconnectHandoff();
        identity.beginTeardown(client, handler, equal1);
        worker(() -> identity.observe(client, handler, equal2));
        identity.finishTeardown();
        reject(identity::poll, "client_disconnect_mismatch");

        // Deliberately discard an unrelated fake Minecraft task queue. The actual production
        // handoff retains its observation and does not depend on any queued Runnable.
        var queueIndependent = new DisconnectHandoff();
        var discardableQueue = new ArrayDeque<Runnable>();
        int[] queuedRuns = { 0 };
        discardableQueue.add(() -> queuedRuns[0]++);
        queueIndependent.beginTeardown(client, handler, connection);
        worker(() -> queueIndependent.observe(client, handler, connection));
        discardableQueue.clear();
        check(queuedRuns[0] == 0 && discardableQueue.isEmpty());
        queueIndependent.finishTeardown();
        check(queueIndependent.poll() == connection);

        // Reentrant owner-tick fixture: only a later invocation may consume after unwind.
        var nested = new DisconnectHandoff();
        int[] consumed = { 0 };
        Runnable ownerTick = () -> {
            if (nested.isTearingDown()) return;
            if (nested.poll() != null) consumed[0]++;
        };
        nested.beginTeardown(client, handler, connection);
        nested.observe(client, handler, connection);
        ownerTick.run();
        check(consumed[0] == 0);
        try { ownerTick.run(); }
        finally { nested.finishTeardown(); }
        check(consumed[0] == 0);
        ownerTick.run();
        check(consumed[0] == 1);

        // Actual require implementation and real threads, not a live Minecraft PLAY callback.
        // The separate compiled-method audit proves PLAY still calls this exact assertion
        // immediately after Minecraft.isSameThread(), before state mutation or qualification.
        Thread owner = Thread.currentThread();
        NonceProbe.require(Thread.currentThread() == owner, "client_wrong_thread");
        check(true);
        worker(() -> {
            try {
                NonceProbe.require(Thread.currentThread() == owner, "client_wrong_thread");
                throw new AssertionError("wrong_thread_assertion_accepted");
            } catch (NonceProbe.ProbeFailure expected) {
                if (!expected.code.equals("client_wrong_thread")) throw new AssertionError(expected);
            }
        });
        check(true);
        System.out.println("ACTUAL_DISCONNECT_HANDOFF assertions=" + checked
                + " PASS; real threads, production handoff, identity/queue/tick fixtures; no live game or PLAY acceptance");
    }

    private static void worker(Runnable operation) {
        var failure = new AtomicReference<Throwable>();
        var ready = new CountDownLatch(1);
        var go = new CountDownLatch(1);
        Thread worker = new Thread(() -> {
            ready.countDown();
            try {
                if (!go.await(2, TimeUnit.SECONDS)) throw new AssertionError("worker_start_timeout");
                operation.run();
            } catch (Throwable problem) { failure.set(problem); }
        }, "disconnect-test-observer");
        worker.setDaemon(true); // A failed test cannot leave a runaway non-daemon test thread.
        worker.start();
        try {
            if (!ready.await(2, TimeUnit.SECONDS)) throw new AssertionError("worker_ready_timeout");
            go.countDown();
            worker.join(2000);
            if (worker.isAlive()) throw new AssertionError("worker_finish_timeout");
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new AssertionError(interrupted);
        } finally {
            go.countDown();
            if (worker.isAlive()) worker.interrupt();
        }
        if (failure.get() != null) throw new AssertionError("worker_failed", failure.get());
    }
    private static void check(boolean value) {
        if (!value) throw new AssertionError("disconnect_handoff_check_" + checked);
        checked++;
    }
    private static void reject(Runnable operation, String code) {
        try { operation.run(); }
        catch (NonceProbe.ProbeFailure expected) { check(expected.code.equals(code)); return; }
        throw new AssertionError("expected_" + code);
    }
    private static final class EqualIdentity {
        @Override public boolean equals(Object other) { return other instanceof EqualIdentity; }
        @Override public int hashCode() { return 1; }
    }
}
