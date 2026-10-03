package org.sinytra.connector.locator;

import net.neoforged.neoforgespi.ILaunchContext;
import net.neoforged.neoforgespi.locating.*;
import org.sinytra.connector.infinity.inventory.AdmissionSession;

/** Defense-in-depth claim/report of the already frozen pre-SERVICE decisions; no directory rescan. */
public final class InfrastructureExclusionLocator implements IModFileCandidateLocator {
    @Override public int getPriority() { return HIGHEST_SYSTEM_PRIORITY + 1000; }
    @Override public void findCandidates(ILaunchContext context, IDiscoveryPipeline pipeline) {
        for (var entry : AdmissionSession.current().snapshot()) {
            if (!entry.decision().mayExecute()) {
                context.addLocated(entry.path());
                AdmittedModCatalog.recordExclusions(entry.decision().exclusions());
            }
        }
    }
}
