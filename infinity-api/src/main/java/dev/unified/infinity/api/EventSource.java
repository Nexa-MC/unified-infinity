package dev.unified.infinity.api;

/** Host-owned emission authority. Keep this handle private and expose only event(). */
public final class EventSource<T> {
    private final Event<T> event;

    private EventSource(String id, Capability capability, Thread thread) {
        event = new Event<>(id, capability, thread);
    }

    /** The host must call this on the actual game/server thread, not a mod-loading worker. */
    public static <T> EventSource<T> onCurrentThread(String id, Capability capability) {
        return new EventSource<>(id, capability, Thread.currentThread());
    }

    public Event<T> event() { return event; }

    /** Synchronous fail-fast dispatch. Caller owns payload allocation and safe lifetime. */
    public void emit(T payload) { event.emit(payload); }
}
