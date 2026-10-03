package dev.unified.infinity.api;

/** Registration failed because the host did not grant a required feature. */
public final class CapabilityException extends IllegalStateException {
    private static final long serialVersionUID = 1L;

    CapabilityException(String modId, String eventId, Capability required) {
        super("Mod '" + modId + "' cannot listen to '" + eventId
                + "': missing capability '" + required.id() + "'");
    }
}
