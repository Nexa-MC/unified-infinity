package dev.unified.infinity.api;

/** Fail-fast listener failure. Earlier callbacks may already have changed game state. */
public final class EventDispatchException extends RuntimeException {
    private static final long serialVersionUID = 1L;
    private final String eventId;
    private final String modId;
    private final int listenerIndex;

    EventDispatchException(String eventId, String modId, int listenerIndex, RuntimeException cause) {
        super("Event '" + eventId + "' failed in mod '" + modId
                + "' at snapshot listener " + listenerIndex, cause);
        this.eventId = eventId;
        this.modId = modId;
        this.listenerIndex = listenerIndex;
    }

    public String eventId() { return eventId; }
    public String modId() { return modId; }
    public int listenerIndex() { return listenerIndex; }
}
