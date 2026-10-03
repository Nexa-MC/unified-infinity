package dev.unified.infinity.api;

import java.util.HashSet;
import java.util.Objects;
import java.util.Set;
import java.util.function.Consumer;

/**
 * Host-created lifetime for one mod/server session. The host must close it at stop,
 * failed initialization, or unload. Capability declarations are not a security sandbox.
 */
public final class ModScope implements AutoCloseable {
    private final String modId;
    private final Set<Capability> capabilities;
    private final Set<OwnedSubscription<?>> subscriptions = new HashSet<>();
    private boolean closed;

    private ModScope(String modId, Set<Capability> capabilities) {
        this.modId = Objects.requireNonNull(modId, "modId");
        if (!modId.matches("[a-z0-9_.-]+")) {
            throw new IllegalArgumentException("Invalid mod id: " + modId);
        }
        this.capabilities = Set.copyOf(capabilities);
    }

    public static ModScope open(String modId, Set<Capability> grantedCapabilities) {
        return new ModScope(modId, Objects.requireNonNull(grantedCapabilities, "grantedCapabilities"));
    }

    public String modId() { return modId; }
    public synchronized boolean isClosed() { return closed; }
    public synchronized int subscriptionCount() { return subscriptions.size(); }

    synchronized <T> Subscription register(Event<T> event, Consumer<? super T> listener) {
        if (closed) {
            throw new IllegalStateException("Mod scope '" + modId + "' is closed; cannot listen to '"
                    + event.id() + "'");
        }
        if (!capabilities.contains(event.requiredCapability())) {
            throw new CapabilityException(modId, event.id(), event.requiredCapability());
        }
        Event.Entry<T> entry = new Event.Entry<>(modId, listener);
        OwnedSubscription<T> subscription = new OwnedSubscription<>(this, event, entry);
        subscriptions.add(subscription);
        event.add(entry);
        return subscription;
    }

    private synchronized void unsubscribe(OwnedSubscription<?> subscription) {
        if (subscription.owner != this) {
            return;
        }
        subscription.detach();
        subscriptions.remove(subscription);
    }

    /**
     * Idempotent and thread-safe. After return, no future snapshot contains these
     * listeners. An already captured snapshot may still invoke them, including later
     * callbacks in the current dispatch. Close on the game thread between dispatches
     * before destroying resources that listeners use.
     */
    @Override
    public synchronized void close() {
        if (closed) {
            return;
        }
        closed = true;
        for (OwnedSubscription<?> subscription : subscriptions) {
            subscription.detach();
        }
        subscriptions.clear();
    }

    private static final class OwnedSubscription<T> implements Subscription {
        private volatile ModScope owner;
        // Read/written only under the owner's monitor. Cleared on detach, so keeping
        // a closed handle does not pin an event, scope, listener, or mod class loader.
        private Event<T> event;
        private Event.Entry<T> entry;

        OwnedSubscription(ModScope owner, Event<T> event, Event.Entry<T> entry) {
            this.owner = owner;
            this.event = event;
            this.entry = entry;
        }

        @Override
        public boolean isClosed() { return owner == null; }

        @Override
        public void close() {
            ModScope currentOwner = owner;
            if (currentOwner != null) {
                currentOwner.unsubscribe(this);
            }
        }

        void detach() {
            event.remove(entry);
            event = null;
            entry = null;
            owner = null;
        }
    }
}
