package org.unifiedinfinity.gatefixture;
import cpw.mods.jarhandling.JarContents;
import net.neoforged.neoforgespi.locating.*;
public final class MarkedReader implements IModFileReader {
    static { Markers.mark("reader-static"); }
    public MarkedReader() { Markers.mark("reader-constructor"); }
    public IModFile read(JarContents contents, ModFileDiscoveryAttributes attributes) { Markers.mark("reader-read"); return null; }
}
