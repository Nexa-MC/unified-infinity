/** Explicit JPMS provider fixture. Compile separately from the META-INF/services variant. */
module unified.admission.fixture {
    requires fml_loader;
    requires cpw.mods.modlauncher;
    provides net.neoforged.neoforgespi.earlywindow.GraphicsBootstrapper with org.unifiedinfinity.gatefixture.MarkedGraphics;
    provides net.neoforged.neoforgespi.earlywindow.ImmediateWindowProvider with org.unifiedinfinity.gatefixture.MarkedWindow;
    provides cpw.mods.modlauncher.api.ITransformationService with org.unifiedinfinity.gatefixture.MarkedTransformer;
    provides net.neoforged.neoforgespi.locating.IModFileCandidateLocator with org.unifiedinfinity.gatefixture.MarkedLocator;
    provides net.neoforged.neoforgespi.locating.IModFileReader with org.unifiedinfinity.gatefixture.MarkedReader;
    provides net.neoforged.neoforgespi.locating.IDependencyLocator with org.unifiedinfinity.gatefixture.MarkedDependency;
}
