package org.unifiedinfinity.gatefixture;
import cpw.mods.modlauncher.api.*;
import java.util.*;
public final class MarkedTransformer implements ITransformationService {
    static { Markers.mark("transformer-static"); }
    public MarkedTransformer() { Markers.mark("transformer-constructor"); }
    public String name() { return "unified-admission-fixture"; }
    public void initialize(IEnvironment environment) { Markers.mark("transformer-initialize"); }
    public void onLoad(IEnvironment environment, Set<String> otherServices) {}
    public List<? extends ITransformer<?>> transformers() { return List.of(); }
}
