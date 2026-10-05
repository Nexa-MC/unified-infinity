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

import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.locks.ReadWriteLock;
import java.util.concurrent.locks.ReentrantReadWriteLock;
import java.util.function.Consumer;

/**
 * Source-only projection of QSL alpha.5 GlobalReceiverRegistry for one PLAY side.
 * It owns receiver selection only. Codecs and native delivery belong to FFAPI.
 * Derived from the source pinned in source-provenance.json; not a QSL ABI facade.
 */
public final class QslPlayReceivers {
    public enum ReceiveSide { CLIENT_S2C, SERVER_C2S }

    /** The host adapter must retain the native payload and connection context. */
    @FunctionalInterface
    public interface Receiver {
        void receive(QslPlayConnection connection, Object decodedPayload);
    }

    private final ReceiveSide side;
    private final Consumer<PlayChannelId> validateGlobalUnregister;
    private final ReadWriteLock lock = new ReentrantReadWriteLock();
    private final Map<PlayChannelId, Receiver> globals = new HashMap<>();
    private final Set<QslPlayConnection> sessions = new HashSet<>();

    /**
     * validateGlobalUnregister is the UNWIRED host assertPayloadType boundary.
     * It must check the correct PLAY/direction codec registry and the source's
     * payload-type toString length rule. No parallel codec registry is created.
     * Alpha.5 calls that check on global unregister, not on registration.
     */
    public QslPlayReceivers(ReceiveSide side, Consumer<PlayChannelId> validateGlobalUnregister) {
        this.side = Objects.requireNonNull(side, "side");
        this.validateGlobalUnregister = Objects.requireNonNull(validateGlobalUnregister, "validateGlobalUnregister");
    }

    ReceiveSide side() {
        return side;
    }

    public Receiver globalReceiver(PlayChannelId id) {
        lock.readLock().lock();
        try {
            return globals.get(id);
        } finally {
            lock.readLock().unlock();
        }
    }

    public boolean registerGlobal(PlayChannelId id, Receiver receiver) {
        Objects.requireNonNull(id, "Channel name cannot be null");
        Objects.requireNonNull(receiver, "Channel handler cannot be null");
        id.requireOrdinaryChannel();
        lock.writeLock().lock();
        try {
            boolean inserted = globals.putIfAbsent(id, receiver) == null;
            if (inserted) {
                // Like QSL, propagation and per-connection hooks occur under the global lock.
                for (QslPlayConnection session : sessions) {
                    session.registerLocal(id, receiver);
                }
            }
            return inserted;
        } finally {
            lock.writeLock().unlock();
        }
    }

    public Receiver unregisterGlobal(PlayChannelId id) {
        Objects.requireNonNull(id, "Channel name cannot be null").requireOrdinaryChannel();
        // Source quirk: this runs even if the global receiver is absent.
        validateGlobalUnregister.accept(id);
        lock.writeLock().lock();
        try {
            Receiver removed = globals.remove(id);
            if (removed != null) {
                for (QslPlayConnection session : sessions) {
                    // No origin tag: this also removes a same-ID local receiver.
                    session.unregisterLocal(id);
                }
            }
            return removed;
        } finally {
            lock.writeLock().unlock();
        }
    }

    /** Mutable, detached snapshot, as returned by GlobalReceiverRegistry.getReceivers. */
    public Map<PlayChannelId, Receiver> globalReceiversSnapshot() {
        // The source takes the write lock here, despite performing a read/copy.
        lock.writeLock().lock();
        try {
            return new HashMap<>(globals);
        } finally {
            lock.writeLock().unlock();
        }
    }

    /** Mutable, detached snapshot, not a view of future registrations. */
    public Set<PlayChannelId> globalChannelsSnapshot() {
        lock.readLock().lock();
        try {
            return new HashSet<>(globals.keySet());
        } finally {
            lock.readLock().unlock();
        }
    }

    void startSession(QslPlayConnection session) {
        lock.writeLock().lock();
        try {
            sessions.add(session);
        } finally {
            lock.writeLock().unlock();
        }
    }

    void endSession(QslPlayConnection session) {
        lock.writeLock().lock();
        try {
            sessions.remove(session);
        } finally {
            lock.writeLock().unlock();
        }
    }
}
