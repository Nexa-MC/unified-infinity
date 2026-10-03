package org.sinytra.connector.infinity;

import cpw.mods.modlauncher.api.*;
import java.util.List;
import java.util.Set;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.fml.loading.unified.CompatibilityComponent;
import net.neoforged.neoforgespi.ILaunchContext;
import net.neoforged.neoforgespi.coremod.ICoreMod;
import net.neoforged.neoforgespi.language.IModLanguageLoader;
import net.neoforged.neoforgespi.locating.*;
import org.sinytra.connector.ConnectorCoremods;
import org.sinytra.connector.forge.discovery.ForgeModFileReader;
import org.sinytra.connector.forge.loader.ForgeModLanguageLoader;
import org.sinytra.connector.locator.*;
import org.sinytra.connector.service.ConnectorLoaderService;

/** FML-owned SERVICE component; upstream implementations retain their attribution. */
public final class FmlCompatibilityComponent implements CompatibilityComponent {
    private final ConnectorLoaderService service = new ConnectorLoaderService();
    private List<IModFileCandidateLocator> candidates;
    private List<IModFileReader> readers;
    private List<IDependencyLocator> dependencies;
    private List<IModLanguageLoader> languages;
    private List<ICoreMod> coremods;

    @Override public void onLoad(IEnvironment environment, Set<String> others) {
        service.onLoad(environment, others);
    }
    @Override public void initialize(IEnvironment environment, ILaunchContext context) {
        service.initialize(environment);
    }
    @Override public List<ITransformationService.Resource> beginScanning(IEnvironment environment) {
        return service.beginScanning(environment);
    }
    @Override public List<ITransformationService.Resource> completeScan(IModuleLayerManager layers) {
        return service.completeScan(layers);
    }
    @Override public List<? extends ITransformer<?>> transformers() { return service.transformers(); }
    @Override public synchronized List<IModFileCandidateLocator> candidateLocators() {
        if (candidates == null) candidates = List.of(new InfrastructureExclusionLocator(), new ConnectorEarlyLocatorBootstrap());
        return candidates;
    }
    @Override public synchronized List<IModFileReader> modFileReaders() {
        if (readers == null) readers = List.of(new HostInfrastructureGuardReader(), new ForgeModFileReader());
        return readers;
    }
    @Override public synchronized List<IDependencyLocator> dependencyLocators() {
        if (dependencies == null) dependencies = List.of(new ConnectorLocator());
        return dependencies;
    }
    @Override public synchronized List<IModLanguageLoader> languageProviders() {
        if (languages == null) languages = List.of(new ForgeModLanguageLoader());
        return languages;
    }
    @Override public synchronized List<ICoreMod> coreMods() {
        if (coremods == null) coremods = List.of(new ConnectorCoremods());
        return coremods;
    }
    @Override public void beforeGameStart(ModuleLayer layer, Dist dist) { service.beforeGameStart(layer); }
}
