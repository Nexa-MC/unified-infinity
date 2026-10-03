package dev.unified.infinity.api;

import java.util.Arrays;
import java.util.Objects;
import java.util.function.Consumer;

/**
 * A typed, synchronous, notification-only event. Mods receive this listen-only handle;
 * the host retains its EventSource. T is the payload type, not a callback interface.
 * Registration and unsubscription are thread-safe. Dispatch is owner-thread-only.
 */
public final class Event<T> {
    private static final Entry<?>[] EMPTY = new Entry<?>[0];
    private final String id;
    private final Capability requiredCapability;
    private final Thread dispatchThread;
    private volatile Entry<?>[] listeners = EMPTY;

    Event(String id, Capability requiredCapability, Thread dispatchThread) {
        this.id = Ids.requireNamespaced(id);
        this.requiredCapability = Objects.requireNonNull(requiredCapability, "requiredCapability");
        this.dispatchThread = Objects.requireNonNull(dispatchThread, "dispatchThread");
    }

    public String id() { return id; }
    public Capability requiredCapability() { return requiredCapability; }
    public int listenerCount() { return listeners.length; }

    /** Call order is successful registration order, including registrations by multiple mods. */
    public Subscription listen(ModScope owner, Consumer<? super T> listener) {
        Objects.requireNonNull(owner, "owner");
        Objects.requireNonNull(listener, "listener");
        return owner.register(this, listener);
    }

    synchronized void add(Entry<T> entry) {
        Entry<?>[] old = listeners;
        Entry<?>[] next = Arrays.copyOf(old, old.length + 1);
        next[old.length] = entry;
        listeners = next;
    }

    synchronized void remove(Entry<T> entry) {
        Entry<?>[] old = listeners;
        for (int index = 0; index < old.length; index++) {
            if (old[index] == entry) {
                if (old.length == 1) {
                    listeners = EMPTY;
                } else {
                    Entry<?>[] next = new Entry<?>[old.length - 1];
                    System.arraycopy(old, 0, next, 0, index);
                    System.arraycopy(old, index + 1, next, index, old.length - index - 1);
                    listeners = next;
                }
                return;
            }
        }
        throw new IllegalStateException("Subscription was not registered on '" + id + "'");
    }

    void emit(T payload) {
        if (Thread.currentThread() != dispatchThread) {
            throw new IllegalStateException("Event '" + id + "' requires owner thread '"
                    + dispatchThread.getName() + "' (" + dispatchThread.threadId()
                    + "), got '" + Thread.currentThread().getName() + "' ("
                    + Thread.currentThread().threadId() + ")");
        }
        Objects.requireNonNull(payload, "payload");
        Entry<?>[] snapshot = listeners;
        for (int index = 0; index < snapshot.length; index++) {
            // Only register(Event<T>, Consumer<? super T>) can construct this event's entries.
            @SuppressWarnings("unchecked")
            Entry<T> entry = (Entry<T>) snapshot[index];
            try {
                entry.listener.accept(payload);
            } catch (RuntimeException failure) {
                throw new EventDispatchException(id, entry.modId, index, failure);
            }
        }
    }

    static final class Entry<T> {
        final String modId;
        final Consumer<? super T> listener;

        Entry(String modId, Consumer<? super T> listener) {
            this.modId = modId;
            this.listener = listener;
        }
    }
}
