/* Unified Infinity installed capability intake. SPDX-License-Identifier: LGPL-2.1-only */
package net.neoforged.fml.loading.unified;

import net.neoforged.neoforgespi.ILaunchContext;
import net.neoforged.neoforgespi.locating.*;
import org.sinytra.connector.infinity.inventory.AdmissionSession;

/** Exact installation-owned roots. Neither directory enumeration nor ordinary compatibility-mod bootstrap. */
public final class InstalledComponentsLocator implements IModFileCandidateLocator {
    @Override public int getPriority() { return HIGHEST_SYSTEM_PRIORITY; }
    @Override public void findCandidates(ILaunchContext context, IDiscoveryPipeline pipeline) {
        var session = AdmissionSession.current();
        for (String role : new String[] { "COMPATIBILITY_GAME", "PRODUCT_GAME" }) {
            var path = session.installedComponent(role);
            pipeline.addPath(path, ModFileDiscoveryAttributes.DEFAULT, IncompatibleFileReporting.ERROR);
        }
    }
}
