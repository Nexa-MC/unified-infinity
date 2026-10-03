package org.unifiedinfinity.gatefixture;
import net.neoforged.neoforgespi.ILaunchContext;
import net.neoforged.neoforgespi.locating.*;
public final class MarkedLocator implements IModFileCandidateLocator {
    static { Markers.mark("locator-static"); }
    public MarkedLocator() { Markers.mark("locator-constructor"); }
    public void findCandidates(ILaunchContext context, IDiscoveryPipeline pipeline) { Markers.mark("locator-find"); }
}
