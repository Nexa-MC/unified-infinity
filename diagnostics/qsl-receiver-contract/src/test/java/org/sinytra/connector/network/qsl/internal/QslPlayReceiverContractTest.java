/* Self-authored source-contract tests, MIT. See LICENSES/Project-MIT.txt. */
package org.sinytra.connector.network.qsl.internal;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;

/**
 * Prepared, NOT COMPILED OR RUN. No dependencies beyond the JDK and this slice.
 * A fake queue and event-loop predicate specify handoff semantics only; they do
 * not prove Minecraft/Netty thread identity, ABI compatibility, or socket delivery.
 */
public final class QslPlayReceiverContractTest {
    private static final PlayChannelId A = new PlayChannelId("probe:a");
    private static final PlayChannelId B = new PlayChannelId("probe:b");
    private static final PlayChannelId C = new PlayChannelId("probe:c");
    private static final QslPlayReceivers.Receiver NOOP = (connection, payload) -> {};

    public static void main(String[] args) {
        globalsCopyBeforeInitAndDeliverOnce();
        constructionTracksBeforeLateInit();
        lateGlobalPreservesLocalThenGlobalRemovalDeletesIt();
        removingCopiedGlobalHasNoFallback();
        absentGlobalUnregisterValidatesWithoutRemovingLocal();
        unregisterValidationFailureLeavesStateUntouched();
        normalDisconnectUntracksAndReconnectCopiesCurrentGlobals();
        snapshotsAndLiveViewDiffer();
        peerStateChangesBeforeQueuedEvents();
        queuedEventsKeepSourceListIdentity();
        pendingPlayChannelsAreConsumedAndCopied();
        channelEventsRemainQueuedAfterDisconnect();
        receiverBoundaryIsInlineAndPreservesFailures();
        wrongThreadRejectsDeliveryAndPeerMutation();
        sourceClientAndServerAdvertisementFlags();
        throwingDisconnectListenerPreservesSourceQuirk();
        lateInitAndReadyHaveNoInventedOnceGuard();
        directionRegistriesRemainIndependent();
        reservedAndNullArgumentsAreRejected();
        failingHooksLeaveSourceMutationInPlace();
        failedInitialReadinessDoesNotEnableDynamicAdvertisements();
        selectedReceiverMayReplaceItselfForTheNextPayload();
        pendingEventsMayRunInlineBeforeSessionTracking();
        disconnectDoesNotInventADeliveryGuard();
        System.out.println("24 QSL receiver source contracts completed; no runtime acceptance claim");
    }

    private static void globalsCopyBeforeInitAndDeliverOnce() {
        var globals = registry();
        var host = new Host();
        var calls = new AtomicInteger();
        Object payload = new Object();
        QslPlayReceivers.Receiver receiver = (connection, actual) -> {
            check(actual == payload, "decoded payload identity changed");
            calls.incrementAndGet();
        };
        check(globals.registerGlobal(A, receiver), "first global registration failed");
        var session = connect(globals, host);
        check(session.receiver(A) == null, "constructor copied globals before lateInit");
        host.atInit = connection -> check(connection.receiver(A) == receiver, "INIT preceded global copy");
        session.lateInit();
        check(!session.registerLocal(A, NOOP), "local registration replaced copied global");
        check(!globals.registerGlobal(A, NOOP), "duplicate global replaced original");
        check(session.deliverDecodedCustomPayload(A, payload), "selected receiver was not handled");
        check(calls.get() == 1 && host.queue.isEmpty(), "receiver queued or delivered twice");
    }

    private static void constructionTracksBeforeLateInit() {
        var globals = registry();
        var session = connect(globals, new Host());
        check(globals.registerGlobal(A, NOOP), "global registration failed");
        check(session.receiver(A) == NOOP, "session was not tracked before lateInit");
        var existing = registry();
        existing.registerGlobal(A, NOOP);
        var beforeInit = connect(existing, new Host());
        QslPlayReceivers.Receiver local = (connection, payload) -> {};
        check(beforeInit.registerLocal(A, local), "local before lateInit failed");
        beforeInit.lateInit();
        check(beforeInit.receiver(A) == local, "lateInit overwrote earlier local");
    }

    private static void lateGlobalPreservesLocalThenGlobalRemovalDeletesIt() {
        var globals = registry();
        var localFirst = connect(globals, new Host());
        var globalFirst = connect(globals, new Host());
        QslPlayReceivers.Receiver local = (connection, payload) -> {};
        localFirst.registerLocal(A, local);
        check(globals.registerGlobal(A, NOOP), "late global registration failed");
        check(localFirst.receiver(A) == local, "late global replaced local");
        check(globalFirst.receiver(A) == NOOP, "late global did not propagate");
        check(globals.unregisterGlobal(A) == NOOP, "wrong global removal return");
        check(localFirst.receiver(A) == null && globalFirst.receiver(A) == null,
                "global unregister must remove effective ID, including prior local");
    }

    private static void removingCopiedGlobalHasNoFallback() {
        var globals = registry();
        globals.registerGlobal(A, NOOP);
        var session = connect(globals, new Host());
        session.lateInit();
        check(session.unregisterLocal(A) == NOOP, "copied global was not removed locally");
        check(globals.globalReceiver(A) == NOOP, "local removal changed global map");
        check(!session.deliverDecodedCustomPayload(A, new Object()), "lookup fell back to global map");
        check(!globals.registerGlobal(A, NOOP), "duplicate global registration succeeded");
        check(session.receiver(A) == null, "duplicate global registration repaired absent local entry");
    }

    private static void absentGlobalUnregisterValidatesWithoutRemovingLocal() {
        var validations = new AtomicInteger();
        var globals = new QslPlayReceivers(QslPlayReceivers.ReceiveSide.SERVER_C2S,
                id -> validations.incrementAndGet());
        var session = connect(globals, new Host());
        session.registerLocal(A, NOOP);
        check(globals.unregisterGlobal(A) == null, "absent global removal returned a handler");
        check(validations.get() == 1, "absent global removal skipped payload-type assertion");
        check(session.receiver(A) == NOOP, "absent global removal touched effective local state");
    }

    private static void unregisterValidationFailureLeavesStateUntouched() {
        var missingCodec = new IllegalArgumentException("host codec absent");
        var validations = new AtomicInteger();
        var globals = new QslPlayReceivers(QslPlayReceivers.ReceiveSide.SERVER_C2S, id -> {
            validations.incrementAndGet();
            throw missingCodec;
        });
        var session = connect(globals, new Host());
        globals.registerGlobal(A, NOOP);
        session.registerLocal(B, NOOP);
        check(validations.get() == 0, "registration invented a codec validation step");
        expectSame(missingCodec, () -> globals.unregisterGlobal(A));
        check(globals.globalReceiver(A) == NOOP && session.receiver(A) == NOOP,
                "unregister mutated state before failed source assertion");
        check(session.unregisterLocal(B) == NOOP && validations.get() == 1,
                "local unregister unexpectedly used global payload assertion");
    }

    private static void normalDisconnectUntracksAndReconnectCopiesCurrentGlobals() {
        var globals = registry();
        var host = new Host();
        var oldSession = connect(globals, host);
        globals.registerGlobal(A, NOOP);
        host.atDisconnect = connection -> globals.registerGlobal(B, NOOP);
        oldSession.disconnect();
        oldSession.disconnect();
        check(host.disconnectCalls == 1, "disconnect notification duplicated");
        check(oldSession.receiver(B) == NOOP, "session untracked before disconnect callback");
        globals.unregisterGlobal(A);
        globals.registerGlobal(C, NOOP);
        check(oldSession.receiver(A) == NOOP && oldSession.receiver(C) == null,
                "normal disconnect cleared state or remained tracked");
        var newSession = connect(globals, new Host());
        newSession.lateInit();
        check(newSession.receiver(A) == null && newSession.receiver(B) == NOOP
                && newSession.receiver(C) == NOOP, "reconnect reused stale receiver state");
    }

    private static void snapshotsAndLiveViewDiffer() {
        var globals = registry();
        var session = connect(globals, new Host());
        globals.registerGlobal(A, NOOP);
        var globalMap = globals.globalReceiversSnapshot();
        var globalIds = globals.globalChannelsSnapshot();
        var localIds = session.receivableChannelsSnapshot();
        var live = session.sendableChannelsView();
        globals.registerGlobal(B, NOOP);
        check(!globalMap.containsKey(B) && !globalIds.contains(B) && !localIds.contains(B),
                "receiver snapshot became live");
        globalMap.clear();
        globalIds.clear();
        localIds.clear();
        check(globals.globalReceiver(A) == NOOP && session.receiver(A) == NOOP,
                "mutating detached snapshot changed source state");
        check(live.isEmpty(), "local receiver or codec knowledge became peer sendability");
        session.receivePeerChannelChange(List.of(A), true);
        check(live.contains(A), "sendable view was a snapshot");
        expect(UnsupportedOperationException.class, () -> live.add(B));
        session.receivePeerChannelChange(List.of(A), false);
        check(!live.contains(A), "sendable view retained removed peer channel");
    }

    private static void peerStateChangesBeforeQueuedEvents() {
        var host = new Host();
        var session = connect(registry(), host);
        List<PlayChannelId> duplicateIds = List.of(A, A);
        session.receivePeerChannelChange(duplicateIds, true);
        session.receivePeerChannelChange(List.of(A, B), false);
        check(session.sendableChannelsView().isEmpty(), "peer membership waited for game callback");
        check(host.peerEvents.isEmpty() && host.queue.size() == 2, "channel events ran inline");
        host.drainGameQueue();
        check(host.peerEvents.size() == 2 && host.peerEvents.get(0).ids() == duplicateIds,
                "duplicate source event IDs were filtered or copied");
        check(host.peerEvents.get(0).register() && !host.peerEvents.get(1).register(),
                "queued event order/flags changed");
        check(host.peerEvents.get(1).ids().contains(B), "absent peer unregister was suppressed");
    }

    private static void queuedEventsKeepSourceListIdentity() {
        var host = new Host();
        var session = connect(registry(), host);
        var ids = new ArrayList<>(List.of(A));
        session.receivePeerChannelChange(ids, true);
        ids.add(B);
        host.drainGameQueue();
        check(host.peerEvents.get(0).ids() == ids && host.peerEvents.get(0).ids().contains(B),
                "source list capture was silently made immutable");
        check(!session.sendableChannelsView().contains(B), "later list mutation changed prior membership update");
    }

    private static void pendingPlayChannelsAreConsumedAndCopied() {
        var host = new Host();
        var pending = new ArrayList<>(List.of(A, B));
        var session = new QslPlayConnection(registry(), host, pending);
        check(pending.isEmpty() && session.sendableChannelsView().equals(Set.of(A, B)),
                "pending PLAY names were not consumed");
        check(host.peerEvents.isEmpty() && host.queue.size() == 1, "pending event was not queued");
        pending.add(C);
        host.drainGameQueue();
        check(host.peerEvents.get(0).ids().equals(List.of(A, B)), "pending collection was not copied");
        check(host.lifecycle.isEmpty(), "constructor fired INIT or JOIN");
    }

    private static void channelEventsRemainQueuedAfterDisconnect() {
        var host = new Host();
        var session = connect(registry(), host);
        session.receivePeerChannelChange(List.of(A), true);
        session.disconnect();
        check(host.peerEvents.isEmpty(), "disconnect synchronously drained queued events");
        host.drainGameQueue();
        check(host.peerEvents.size() == 1 && session.sendableChannelsView().contains(A),
                "disconnect cancelled source callback or cleared peer state");
    }

    private static void receiverBoundaryIsInlineAndPreservesFailures() {
        var host = new Host();
        var session = connect(registry(), host);
        var calls = new AtomicInteger();
        Thread receiving = Thread.currentThread();
        session.registerLocal(A, (actualSession, payload) -> {
            check(actualSession == session && Thread.currentThread() == receiving, "receiver context/thread changed");
            calls.incrementAndGet();
        });
        check(session.deliverDecodedCustomPayload(A, new Object()), "known payload unhandled");
        check(calls.get() == 1 && host.queue.isEmpty(), "receiver ran through game queue");
        check(!session.deliverDecodedCustomPayload(B, new Object()), "unknown payload considered handled");
        var failure = new IllegalStateException("mod receiver failed");
        session.registerLocal(B, (connection, payload) -> { throw failure; });
        expectSame(failure, () -> session.deliverDecodedCustomPayload(B, new Object()));
    }

    private static void wrongThreadRejectsDeliveryAndPeerMutation() {
        var host = new Host();
        var session = connect(registry(), host);
        var calls = new AtomicInteger();
        session.registerLocal(A, (connection, payload) -> calls.incrementAndGet());
        host.networkThread = false;
        expect(IllegalStateException.class, () -> session.deliverDecodedCustomPayload(A, new Object()));
        expect(IllegalStateException.class, () -> session.receivePeerChannelChange(List.of(A), true));
        check(calls.get() == 0 && host.queue.isEmpty() && session.sendableChannelsView().isEmpty(),
                "wrong-thread boundary executed receiver or changed peer state");
    }

    private static void sourceClientAndServerAdvertisementFlags() {
        for (var side : QslPlayReceivers.ReceiveSide.values()) {
            var host = new Host();
            var globals = new QslPlayReceivers(side, id -> {});
            var session = connect(globals, host);
            session.registerLocal(A, NOOP);
            check(host.advertisements.isEmpty(), "channel advertised before readiness");
            host.atJoin = connection -> connection.registerLocal(B, NOOP);
            session.ready();
            check(host.lifecycle.equals(List.of("JOIN", "ADVERTISE")), "JOIN/initial-send order changed");
            check(host.advertisements.size() == 1
                    && Set.copyOf(host.advertisements.get(0).ids()).equals(Set.of(A, B)),
                    "JOIN registration was separately advertised or omitted from initial list");
            check(!session.registerLocal(A, NOOP), "duplicate local registration accepted");
            session.registerLocal(C, NOOP);
            session.unregisterLocal(C);
            session.unregisterLocal(C);
            check(host.advertisements.size() == 3, "duplicate register/absent unregister advertised");
            check(host.advertisements.get(1).register(), "dynamic registration used unregister flag");
            check(host.advertisements.get(2).register() == (side == QslPlayReceivers.ReceiveSide.CLIENT_S2C),
                    "alpha.5 client/server unregister flag difference lost");
        }
    }

    private static void throwingDisconnectListenerPreservesSourceQuirk() {
        var globals = registry();
        var host = new Host();
        var session = connect(globals, host);
        var failure = new IllegalStateException("disconnect listener failed");
        host.atDisconnect = connection -> { throw failure; };
        expectSame(failure, session::disconnect);
        session.disconnect();
        globals.registerGlobal(A, NOOP);
        check(host.disconnectCalls == 1 && session.receiver(A) == NOOP,
                "source's failed disconnect attempt was retried or session automatically untracked");
    }

    private static void lateInitAndReadyHaveNoInventedOnceGuard() {
        var globals = registry();
        globals.registerGlobal(A, NOOP);
        var host = new Host();
        var session = connect(globals, host);
        session.lateInit();
        session.unregisterLocal(A);
        session.lateInit();
        check(session.receiver(A) == NOOP && host.initCalls == 2, "lateInit was given a new once guard");
        session.ready();
        session.ready();
        check(host.joinCalls == 2 && host.advertisements.size() == 2, "ready was given a new once guard");
    }

    private static void directionRegistriesRemainIndependent() {
        var clientGlobals = new QslPlayReceivers(QslPlayReceivers.ReceiveSide.CLIENT_S2C, id -> {});
        var serverGlobals = registry();
        var client = connect(clientGlobals, new Host());
        var server = connect(serverGlobals, new Host());
        clientGlobals.registerGlobal(A, NOOP);
        check(client.receiver(A) == NOOP && server.receiver(A) == null, "PLAY directions shared receiver state");
        server.receivePeerChannelChange(List.of(A), true);
        check(server.sendableChannelsView().contains(A) && client.sendableChannelsView().isEmpty(),
                "connections shared peer advertisement state");
    }

    private static void reservedAndNullArgumentsAreRejected() {
        var validations = new AtomicInteger();
        var globals = new QslPlayReceivers(QslPlayReceivers.ReceiveSide.SERVER_C2S,
                id -> validations.incrementAndGet());
        var session = connect(globals, new Host());
        for (String name : List.of("minecraft:register", "minecraft:unregister")) {
            var reserved = new PlayChannelId(name);
            expect(IllegalArgumentException.class, () -> globals.registerGlobal(reserved, NOOP));
            expect(IllegalArgumentException.class, () -> globals.unregisterGlobal(reserved));
            expect(IllegalArgumentException.class, () -> session.registerLocal(reserved, NOOP));
            expect(IllegalArgumentException.class, () -> session.unregisterLocal(reserved));
            expect(IllegalArgumentException.class, () -> session.deliverDecodedCustomPayload(reserved, new Object()));
        }
        check(validations.get() == 0, "reserved rejection called payload validator");
        expect(NullPointerException.class, () -> globals.registerGlobal(null, NOOP));
        expect(NullPointerException.class, () -> globals.registerGlobal(A, null));
        expect(NullPointerException.class, () -> globals.unregisterGlobal(null));
        expect(NullPointerException.class, () -> session.registerLocal(null, NOOP));
        expect(NullPointerException.class, () -> session.registerLocal(A, null));
        expect(NullPointerException.class, () -> session.unregisterLocal(null));
    }

    private static void failingHooksLeaveSourceMutationInPlace() {
        var globals = registry();
        var host = new Host();
        var session = connect(globals, host);
        session.ready();
        var failure = new IllegalStateException("native send failed");
        host.advertisementFailure = failure;
        expectSame(failure, () -> globals.registerGlobal(A, NOOP));
        check(globals.globalReceiver(A) == NOOP && session.receiver(A) == NOOP,
                "failed advertisement rolled back source registration");
        expectSame(failure, () -> globals.unregisterGlobal(A));
        check(globals.globalReceiver(A) == null && session.receiver(A) == null,
                "failed advertisement rolled back source removal");
        host.queueFailure = failure;
        expectSame(failure, () -> session.receivePeerChannelChange(List.of(B), true));
        check(session.sendableChannelsView().contains(B), "failed executor submission rolled back peer state");
    }

    private static void failedInitialReadinessDoesNotEnableDynamicAdvertisements() {
        var host = new Host();
        var session = connect(registry(), host);
        var failure = new IllegalStateException("readiness hook failed");
        host.atJoin = connection -> { throw failure; };
        expectSame(failure, session::ready);
        session.registerLocal(A, NOOP);
        check(host.advertisements.isEmpty(), "failed JOIN enabled dynamic advertisements");
        host.atJoin = connection -> {};
        host.advertisementFailure = failure;
        expectSame(failure, session::ready);
        // This must not call the still-failing advertisement hook.
        session.registerLocal(B, NOOP);
        check(host.advertisements.isEmpty(), "failed initial send enabled dynamic advertisements");
        host.advertisementFailure = null;
        session.ready();
        session.registerLocal(C, NOOP);
        check(host.advertisements.size() == 2
                && Set.copyOf(host.advertisements.get(0).ids()).equals(Set.of(A, B))
                && host.advertisements.get(1).ids().equals(List.of(C)),
                "successful retry failed to advertise current state or enable dynamic updates");
    }

    private static void selectedReceiverMayReplaceItselfForTheNextPayload() {
        var session = connect(registry(), new Host());
        var firstCalls = new AtomicInteger();
        var nextCalls = new AtomicInteger();
        QslPlayReceivers.Receiver replacement = (connection, payload) -> nextCalls.incrementAndGet();
        QslPlayReceivers.Receiver first = (connection, payload) -> {
            firstCalls.incrementAndGet();
            check(connection.unregisterLocal(A) != null, "self-unregistration did not remove selected receiver");
            check(connection.registerLocal(A, replacement), "self-replacement failed");
        };
        session.registerLocal(A, first);
        session.deliverDecodedCustomPayload(A, new Object());
        check(firstCalls.get() == 1 && nextCalls.get() == 0, "one payload selected more than one receiver");
        session.deliverDecodedCustomPayload(A, new Object());
        check(firstCalls.get() == 1 && nextCalls.get() == 1, "next payload retained stale selection");
    }

    private static void pendingEventsMayRunInlineBeforeSessionTracking() {
        var globals = registry();
        var host = new Host();
        host.inlineGameExecutor = true;
        host.atPeerChannels = connection -> {
            check(connection.sendableChannelsView().contains(A), "inline event preceded peer membership update");
            globals.registerGlobal(B, NOOP);
            check(connection.receiver(B) == null, "constructor tracked session before consuming pending channels");
        };
        var pending = new ArrayList<>(List.of(A));
        var session = new QslPlayConnection(globals, host, pending);
        check(host.peerEvents.size() == 1 && host.queue.isEmpty() && pending.isEmpty(),
                "projection forced another queue around host inline execution");
        session.lateInit();
        check(session.receiver(B) == NOOP, "lateInit missed global created by inline pending callback");
    }

    private static void disconnectDoesNotInventADeliveryGuard() {
        var globals = registry();
        var session = connect(globals, new Host());
        var calls = new AtomicInteger();
        session.registerLocal(A, (connection, payload) -> calls.incrementAndGet());
        session.disconnect();
        check(session.deliverDecodedCustomPayload(A, new Object()) && calls.get() == 1,
                "projection added an upstream-absent disconnected delivery guard");
        globals.registerGlobal(B, NOOP);
        check(session.receiver(B) == null, "retained direct method access re-tracked the session");
    }

    private static QslPlayReceivers registry() {
        // Selection tests stub an external assertion; this is not a codec registry.
        return new QslPlayReceivers(QslPlayReceivers.ReceiveSide.SERVER_C2S, id -> {});
    }

    private static QslPlayConnection connect(QslPlayReceivers globals, Host host) {
        return new QslPlayConnection(globals, host, new ArrayList<>());
    }

    private record Notice(List<PlayChannelId> ids, boolean register) {}

    private static final class Host implements QslPlayConnection.HostHooks {
        final ArrayDeque<Runnable> queue = new ArrayDeque<>();
        final List<Notice> advertisements = new ArrayList<>();
        final List<Notice> peerEvents = new ArrayList<>();
        final List<String> lifecycle = new ArrayList<>();
        Consumer<QslPlayConnection> atInit = connection -> {};
        Consumer<QslPlayConnection> atJoin = connection -> {};
        Consumer<QslPlayConnection> atDisconnect = connection -> {};
        Consumer<QslPlayConnection> atPeerChannels = connection -> {};
        boolean networkThread = true;
        boolean inlineGameExecutor;
        boolean drainingGameQueue;
        int initCalls;
        int joinCalls;
        int disconnectCalls;
        RuntimeException advertisementFailure;
        RuntimeException queueFailure;

        @Override public boolean isReceivingEventLoop() { return networkThread; }
        @Override public void executeOnGameThread(Runnable callback) {
            if (queueFailure != null) throw queueFailure;
            if (inlineGameExecutor) {
                drainingGameQueue = true;
                try {
                    callback.run();
                } finally {
                    drainingGameQueue = false;
                }
            } else {
                queue.add(callback);
            }
        }
        @Override public void onInit(QslPlayConnection connection) {
            lifecycle.add("INIT");
            initCalls++;
            atInit.accept(connection);
        }
        @Override public void onJoin(QslPlayConnection connection) {
            lifecycle.add("JOIN");
            joinCalls++;
            atJoin.accept(connection);
        }
        @Override public void onDisconnect(QslPlayConnection connection) {
            lifecycle.add("DISCONNECT");
            disconnectCalls++;
            atDisconnect.accept(connection);
        }
        @Override public void onPeerChannels(QslPlayConnection connection, List<PlayChannelId> ids, boolean register) {
            check(drainingGameQueue, "channel event did not use supplied game executor");
            peerEvents.add(new Notice(ids, register));
            atPeerChannels.accept(connection);
        }
        @Override public void advertiseReceivers(QslPlayConnection connection, List<PlayChannelId> ids, boolean register) {
            if (advertisementFailure != null) throw advertisementFailure;
            lifecycle.add("ADVERTISE");
            advertisements.add(new Notice(ids, register));
        }
        void drainGameQueue() {
            drainingGameQueue = true;
            try {
                while (!queue.isEmpty()) queue.remove().run();
            } finally {
                drainingGameQueue = false;
            }
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    private static void expect(Class<? extends RuntimeException> expected, Runnable action) {
        try {
            action.run();
        } catch (RuntimeException actual) {
            if (expected.isInstance(actual)) return;
            throw actual;
        }
        throw new AssertionError("Expected " + expected.getName());
    }

    private static void expectSame(RuntimeException expected, Runnable action) {
        try {
            action.run();
        } catch (RuntimeException actual) {
            check(actual == expected, "exception identity changed");
            return;
        }
        throw new AssertionError("Expected the original failure");
    }
}
