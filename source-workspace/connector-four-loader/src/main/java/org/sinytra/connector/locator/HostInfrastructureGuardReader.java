package org.sinytra.connector.locator;

import cpw.mods.jarhandling.JarContents;
import net.neoforged.neoforgespi.locating.*;
import org.sinytra.connector.infinity.inventory.AdmissionSession;

/** Every constituent of host/native/JiJ input must have a BOOT-owned object receipt. */
public final class HostInfrastructureGuardReader implements IModFileReader {
    @Override public int getPriority() { return HIGHEST_SYSTEM_PRIORITY + 2000; }
    @Override public IModFile read(JarContents contents, ModFileDiscoveryAttributes attributes) {
        if (!AdmissionSession.current().permitsRuntimeObject(contents))
            throw new IllegalStateException("Excluded host input reached reader transaction: " + contents.getPrimaryPath());
        return null; // Admitted content proceeds to its actual native/Forge reader, with no rescan.
    }
}
