package org.unifiedinfinity.gatefixture;
import net.neoforged.neoforgespi.earlywindow.GraphicsBootstrapper;
public final class MarkedGraphics implements GraphicsBootstrapper {
    static { Markers.mark("graphics-static"); }
    public MarkedGraphics() { Markers.mark("graphics-constructor"); }
    public String name() { return "unified-admission-fixture"; }
    public void bootstrap(String[] arguments) { Markers.mark("graphics-bootstrap"); }
}
