/* Self-authored internal boundary type, MIT. See LICENSES/Project-MIT.txt. */
package org.sinytra.connector.network.qsl.internal;

import java.util.Objects;

/**
 * An already-normalized payload ID supplied by the host's mapped payload type.
 * This is not an Identifier parser, a codec registration, or a public QSL type.
 */
public record PlayChannelId(String value) {
    public PlayChannelId {
        Objects.requireNonNull(value, "Channel name cannot be null");
    }

    boolean isReserved() {
        return value.equals("minecraft:register") || value.equals("minecraft:unregister");
    }

    void requireOrdinaryChannel() {
        if (isReserved()) {
            throw new IllegalArgumentException("Cannot register/unregister a receiver for reserved channel " + value);
        }
    }
}
