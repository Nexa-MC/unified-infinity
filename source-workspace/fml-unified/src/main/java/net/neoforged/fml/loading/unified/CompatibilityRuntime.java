/* Unified Infinity internal source-fusion owner. SPDX-License-Identifier: LGPL-2.1-only */
package net.neoforged.fml.loading.unified;

import cpw.mods.jarhandling.SecureJar;
import cpw.mods.modlauncher.api.*;
import cpw.mods.niofs.union.UnionFileSystem;
import java.net.URI;
import java.nio.file.*;
import java.util.*;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.bus.api.*;
import net.neoforged.fml.event.IModBusEvent;
import net.neoforged.fml.event.lifecycle.*;
import net.neoforged.jarjar.nio.pathfs.PathFileSystem;
import net.neoforged.neoforgespi.ILaunchContext;
import org.jetbrains.annotations.ApiStatus;
import org.sinytra.connector.infinity.inventory.AdmissionSession;
import static net.neoforged.fml.loading.unified.GameCompatibilityComponent.LifecyclePhase;

/** Exactly one FML-owned SERVICE/GAME initialization route. Not a public mod-author API. */
@ApiStatus.Internal
public final class CompatibilityRuntime {
    private static final String SERVICE_CLASS = "org.sinytra.connector.infinity.FmlCompatibilityComponent";
    private static final String GAME_CLASS = "org.sinytra.connector.mod.FmlGameCompatibilityComponent";
    private static final String PRODUCT_CLASS = "dev.modcompat.runtime.bundle.RuntimeBundle";
    private static CompatibilityComponent component;
    private static GameCompatibilityComponent gameComponent, productComponent;
    private static RuntimeException lifecycleFailure;
    private static IEventBus internalBus;
    private static boolean loaded, initialized, scanBegun, scanCompleted, gameStarted, gameInitialized;
    private static final Set<LifecyclePhase> phases = EnumSet.noneOf(LifecyclePhase.class);
    private CompatibilityRuntime() {}

    public static synchronized void onLoad(IEnvironment environment, Set<String> otherServices) throws IncompatibleEnvironmentException {
        if (loaded) throw new IllegalStateException("Internal compatibility onLoad invoked twice");
        loaded = true;
        var layers = environment.findModuleLayerManager().orElseThrow();
        var serviceLayer = layers.getLayer(IModuleLayerManager.Layer.SERVICE).orElseThrow();
        component = instantiate(serviceLayer, AdmissionSession.current().installedComponent("ADMISSION_CONSUMER"), SERVICE_CLASS, CompatibilityComponent.class);
        component.onLoad(environment, Set.copyOf(otherServices));
    }
    public static CompatibilityComponent component() {
        if (component == null) throw new IllegalStateException("FML has not initialized the installed compatibility component");
        return component;
    }
    public static synchronized void initialize(IEnvironment environment, ILaunchContext context) {
        if (initialized) throw new IllegalStateException("Internal compatibility initialize invoked twice");
        initialized = true; component().initialize(environment, context);
    }
    public static synchronized List<ITransformationService.Resource> beginScanning(IEnvironment environment) {
        if (!initialized || scanBegun) throw new IllegalStateException("Internal compatibility scan ordering violation");
        scanBegun = true; return List.copyOf(component().beginScanning(environment));
    }
    public static synchronized List<ITransformationService.Resource> completeScan(IModuleLayerManager layers) {
        if (!scanBegun || scanCompleted) throw new IllegalStateException("Internal compatibility scan completion ordering violation");
        scanCompleted = true;
        List<ITransformationService.Resource> resources = new ArrayList<>(component().completeScan(layers));
        // GAME capability roots enter through InstalledComponentsLocator so original versions,
        // dependencies and mixin declarations remain visible to FML's real validation pipeline.
        if (!net.neoforged.fml.loading.LoadingModList.get().hasErrors()) {
            for (String role : List.of("COMPATIBILITY_GAME", "PRODUCT_GAME")) {
                Path expected = AdmissionSession.current().installedComponent(role);
                boolean selected = net.neoforged.fml.loading.LoadingModList.get().getModFiles().stream()
                    .anyMatch(file -> AdmissionSession.current().sourcePathsForRuntimeObject(file.getFile()).contains(expected));
                if (!selected) throw new IllegalStateException("Installed GAME capability metadata was not selected: " + role);
            }
        }
        return List.copyOf(resources);
    }
    public static synchronized void beforeGameStart(ModuleLayer gameLayer, Dist dist) {
        if (!scanCompleted || gameStarted) throw new IllegalStateException("Internal compatibility GAME ordering violation");
        gameStarted = true;
        if (!net.neoforged.fml.loading.LoadingModList.get().hasErrors()) component().beforeGameStart(gameLayer, dist);
    }
    /** Called after final real ModList installation, before ordinary mod construction begins. */
    public static synchronized void initializeGame(ModuleLayer layer, Dist dist) {
        if (!gameStarted || gameInitialized) throw new IllegalStateException("Internal GAME initialization ordering violation");
        gameInitialized = true;
        gameComponent = instantiate(layer, AdmissionSession.current().installedComponent("COMPATIBILITY_GAME"), GAME_CLASS, GameCompatibilityComponent.class);
        internalBus = BusBuilder.builder().markerType(IModBusEvent.class).allowPerPhasePost().build();
        gameComponent.initialize(internalBus, dist);
        productComponent = instantiate(layer, AdmissionSession.current().installedComponent("PRODUCT_GAME"), PRODUCT_CLASS, GameCompatibilityComponent.class);
        productComponent.initialize(internalBus, dist);
    }
    /** A shared event is posted exactly once at each native priority, ahead of ordinary mod buses. */
    public static <T extends Event & IModBusEvent> void postShared(EventPriority priority, T event) {
        if (event instanceof ModLifecycleEvent) throw new IllegalArgumentException("Container-bound lifecycle events require the typed internal lifecycle route");
        IEventBus bus = internalBus;
        if (bus != null) bus.post(priority, event);
    }
    /** Observe the type of an actual host-created event. Never synthesize an event or fake ModContainer. */
    public static synchronized void observeLifecycle(ParallelDispatchEvent event) {
        if (!gameInitialized) throw new IllegalStateException("GAME component must initialize before lifecycle events");
        LifecyclePhase phase = event instanceof FMLCommonSetupEvent ? LifecyclePhase.COMMON_SETUP
            : event instanceof FMLClientSetupEvent ? LifecyclePhase.CLIENT_SETUP
            : event instanceof FMLDedicatedServerSetupEvent ? LifecyclePhase.DEDICATED_SERVER_SETUP
            : event instanceof InterModEnqueueEvent ? LifecyclePhase.ENQUEUE_IMC
            : event instanceof InterModProcessEvent ? LifecyclePhase.PROCESS_IMC
            : event instanceof FMLLoadCompleteEvent ? LifecyclePhase.LOAD_COMPLETE : null;
        if (lifecycleFailure != null) throw lifecycleFailure;
        if (phase != null && phases.add(phase)) {
            try { gameComponent.onLifecycle(phase); productComponent.onLifecycle(phase); }
            catch (RuntimeException failure) { lifecycleFailure = failure; throw failure; }
        }
    }
    /** Guard accidental retained SPI descriptors before their constructors execute. */
    public static void rejectAutonomousProvider(Class<?> provider) {
        if (!AdmissionSession.isInstalled()) return;
        Path source = classSource(provider);
        if (AdmissionSession.current().installedComponents("ADMISSION_CONSUMER").contains(source))
            throw new IllegalStateException("Installed compatibility provider must be scheduled by FML, not autonomous SPI: " + provider.getName());
    }
    private static <T> T instantiate(ModuleLayer layer, Path expected, String name, Class<T> contract) {
        try {
            Module owner = org.sinytra.connector.infinity.inventory.ArchiveOrigins.componentModule(layer, expected, name);
            Class<?> type = Class.forName(owner, name); // Module-scoped load does not initialize the class.
            if (type == null || !contract.isAssignableFrom(type) || !classSource(type).equals(expected.toRealPath()))
                throw new IllegalStateException("Installed component contract or actual origin mismatch: " + name);
            if (!AdmissionSession.current().permits(List.of(expected))) throw new IllegalStateException("Installed component was denied before construction");
            AdmissionSession.current().bindInstalledModule(owner, expected);
            return contract.cast(type.getConstructor().newInstance());
        } catch (ReflectiveOperationException | java.io.IOException e) {
            throw new IllegalStateException("Cannot initialize the source-owned compatibility component " + name, e);
        }
    }
    private static Path classSource(Class<?> type) {
        try {
            var codeSource = type.getProtectionDomain().getCodeSource();
            if (codeSource == null) throw new IllegalStateException("Component has no code source");
            return sourcePath(codeSource.getLocation().toURI());
        } catch (java.net.URISyntaxException | java.io.IOException e) { throw new IllegalStateException("Cannot establish component code origin", e); }
    }
    private static Path sourcePath(URI uri) throws java.io.IOException {
        return org.sinytra.connector.infinity.inventory.ArchiveOrigins.physical(uri);
    }
}
