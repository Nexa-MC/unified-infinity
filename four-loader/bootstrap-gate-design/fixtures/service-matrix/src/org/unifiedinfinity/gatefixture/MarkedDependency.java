package org.unifiedinfinity.gatefixture;
import net.neoforged.neoforgespi.locating.*;
import java.util.List;
public final class MarkedDependency implements IDependencyLocator {
    static { Markers.mark("dependency-static"); }
    public MarkedDependency() { Markers.mark("dependency-constructor"); }
    public void scanMods(List<IModFile> files, IDiscoveryPipeline pipeline) { Markers.mark("dependency-scan"); }
}
