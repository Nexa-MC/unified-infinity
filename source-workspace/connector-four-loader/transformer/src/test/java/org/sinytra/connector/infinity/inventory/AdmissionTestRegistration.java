package org.sinytra.connector.infinity.inventory;

/** Test-only owner for pinned generated host fixtures. Never included in a runtime archive. */
public final class AdmissionTestRegistration {
    private AdmissionTestRegistration() {}
    public static void begin() { TrustedPayloads.beginRegistration(); }
    public static void seal() { TrustedPayloads.sealRegistration(); }
}
