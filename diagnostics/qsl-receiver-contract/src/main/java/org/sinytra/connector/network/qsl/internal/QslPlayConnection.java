/*
 * Copyright 2016, 2017, 2018, 2019 FabricMC
 * Copyright 2022 The Quilt Project
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package org.sinytra.connector.network.qsl.internal;

import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.locks.ReadWriteLock;
import java.util.concurrent.locks.ReentrantReadWriteLock;

/**
 * Bounded source projection of the alpha.5 abstract and client/server PLAY addons.
 * One instance belongs to one real host play listener and one inbound direction.
 * This class neither subscribes to events nor registers/sends native packets.
 */
public final class QslPlayConnection {
    /**
     * Mandatory host boundaries, deliberately UNWIRED in this source checkpoint.
     * The adapter invokes existing QSL events and the existing host executor;
     * these are not another event bus, executor, transport, or PacketSender API.
     */
    public interface HostHooks {
        boolean isReceivingEventLoop();
        void executeOnGameThread(Runnable callback);
        void onInit(QslPlayConnection connection);
        void onJoin(QslPlayConnection connection);
        void onDisconnect(QslPlayConnection connection);
        void onPeerChannels(QslPlayConnection connection, List<PlayChannelId> ids, boolean register);

        /** Observe/request the source advertisement flag; native encoding/sending is not implemented. */
        void advertiseReceivers(QslPlayConnection connection, List<PlayChannelId> ids, boolean register);
    }

    private final QslPlayReceivers globals;
    private final HostHooks host;
    private final ReadWriteLock lock = new ReentrantReadWriteLock();
    private final Map<PlayChannelId, QslPlayReceivers.Receiver> effectiveReceivers = new HashMap<>();
    private final Set<PlayChannelId> sendableChannels = Collections.synchronizedSet(new HashSet<>());
    private final AtomicBoolean disconnected = new AtomicBoolean();
    private boolean sentInitialAdvertisement;

    /**
     * Mirrors constructor order: consume pending PLAY channel names, then track.
     * Global receivers are copied later in lateInit, not in the constructor.
     * pendingPeerChannels is the host-owned pending collection and is cleared.
     */
    public QslPlayConnection(QslPlayReceivers globals, HostHooks host,
                             Collection<PlayChannelId> pendingPeerChannels) {
        this.globals = Objects.requireNonNull(globals, "globals");
        this.host = Objects.requireNonNull(host, "host");
        Objects.requireNonNull(pendingPeerChannels, "pendingPeerChannels");
        if (!pendingPeerChannels.isEmpty()) {
            updatePeerChannels(new ArrayList<>(pendingPeerChannels), true);
            pendingPeerChannels.clear();
        }
        globals.startSession(this);
    }

    /**
     * Preserve the source's snapshot-then-copy sequence, including its race window.
     * No atomic snapshot/session transaction or once-only INIT guard is invented.
     */
    public void lateInit() {
        for (var entry : globals.globalReceiversSnapshot().entrySet()) {
            registerLocal(entry.getKey(), entry.getValue());
        }
        host.onInit(this);
    }

    public QslPlayReceivers.Receiver receiver(PlayChannelId id) {
        lock.readLock().lock();
        try {
            return effectiveReceivers.get(id);
        } finally {
            lock.readLock().unlock();
        }
    }

    /** Globals and local registrations share this one putIfAbsent map. */
    public boolean registerLocal(PlayChannelId id, QslPlayReceivers.Receiver receiver) {
        Objects.requireNonNull(id, "Channel name cannot be null");
        Objects.requireNonNull(receiver, "Packet handler cannot be null");
        id.requireOrdinaryChannel();
        lock.writeLock().lock();
        try {
            boolean inserted = effectiveReceivers.putIfAbsent(id, receiver) == null;
            if (inserted && sentInitialAdvertisement) {
                host.advertiseReceivers(this, List.of(id), true);
            }
            return inserted;
        } finally {
            lock.writeLock().unlock();
        }
    }

    public QslPlayReceivers.Receiver unregisterLocal(PlayChannelId id) {
        Objects.requireNonNull(id, "Channel name cannot be null").requireOrdinaryChannel();
        lock.writeLock().lock();
        try {
            QslPlayReceivers.Receiver removed = effectiveReceivers.remove(id);
            if (removed != null && sentInitialAdvertisement) {
                // Exact alpha.5 quirk: CLIENT passes true; SERVER passes false.
                boolean registerFlag = globals.side() == QslPlayReceivers.ReceiveSide.CLIENT_S2C;
                host.advertiseReceivers(this, List.of(id), registerFlag);
            }
            return removed;
        } finally {
            lock.writeLock().unlock();
        }
    }

    /** Mutable, detached snapshot; a removed copied global has no fallback. */
    public Set<PlayChannelId> receivableChannelsSnapshot() {
        lock.readLock().lock();
        try {
            return new HashSet<>(effectiveReceivers.keySet());
        } finally {
            lock.readLock().unlock();
        }
    }

    /** JOIN, initial advertisement, then the dynamic-advertisement flag, as upstream. */
    public void ready() {
        host.onJoin(this);
        host.advertiseReceivers(this, List.copyOf(receivableChannelsSnapshot()), true);
        sentInitialAdvertisement = true;
    }

    /**
     * Called exactly once from FFAPI's existing native handler, after admission,
     * decode, phase/direction/listener resolution, and reserved-payload handling.
     * Object carries the unchanged native decoded payload to an ABI-bound adapter.
     * The event-loop assertion is an integration guard, not additional QSL state.
     */
    public boolean deliverDecodedCustomPayload(PlayChannelId id, Object decodedPayload) {
        Objects.requireNonNull(id, "id").requireOrdinaryChannel();
        requireReceivingEventLoop();
        QslPlayReceivers.Receiver selected = receiver(id);
        if (selected == null) {
            return false;
        }
        // Do not enqueue, fan out to a second receiver, or swallow its exception.
        selected.receive(this, decodedPayload);
        return true;
    }

    /** Host-decoded minecraft:(un)register payload only; this does not negotiate it. */
    public void receivePeerChannelChange(List<PlayChannelId> ids, boolean register) {
        requireReceivingEventLoop();
        updatePeerChannels(Objects.requireNonNull(ids, "ids"), register);
    }

    private void updatePeerChannels(List<PlayChannelId> ids, boolean register) {
        if (register) {
            sendableChannels.addAll(ids);
        } else {
            ids.forEach(sendableChannels::remove);
        }
        // Source captures this exact list, including duplicates and later mutations.
        // Membership changes immediately; only the event uses the game executor.
        host.executeOnGameThread(() -> host.onPeerChannels(this, ids, register));
    }

    /**
     * Unmodifiable LIVE view over the synchronized peer-advertised set, as QSL.
     * contains/size reflect later updates. Iteration is not a concurrent snapshot.
     * Codec existence and local receiver presence never add an entry to this set.
     */
    public Set<PlayChannelId> sendableChannelsView() {
        return Collections.unmodifiableSet(sendableChannels);
    }

    /**
     * Exactly-once notification attempt. The source invokes the event before
     * untracking, without finally: a throwing listener leaves the session tracked.
     * Normal disconnect does not clear maps or cancel queued channel callbacks.
     */
    public void disconnect() {
        if (disconnected.compareAndSet(false, true)) {
            host.onDisconnect(this);
            globals.endSession(this);
        }
    }

    private void requireReceivingEventLoop() {
        if (!host.isReceivingEventLoop()) {
            throw new IllegalStateException("QSL play receiver entered outside the host receiving event loop");
        }
    }
}
