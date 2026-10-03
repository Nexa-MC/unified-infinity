package org.sinytra.connector.mod;

import java.util.EnumSet;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.ModList;
import org.sinytra.connector.locator.AdmittedModCatalog;
import net.neoforged.fml.loading.unified.GameCompatibilityComponent;

/** Explicit GAME lifecycle owner; no ordinary compatibility mod is constructed. */
public final class FmlGameCompatibilityComponent implements GameCompatibilityComponent {
    private final EnumSet<LifecyclePhase> phases = EnumSet.noneOf(LifecyclePhase.class);
    private Dist dist;
    private boolean initialized;

    @Override public synchronized void initialize(IEventBus bus, Dist side) {
        if (initialized) throw new IllegalStateException("Compatibility GAME component initialized twice");
        initialized = true;
        dist = java.util.Objects.requireNonNull(side);
        ModList selected = java.util.Objects.requireNonNull(ModList.get(), "Final ModList is unavailable");
        selected.getSortedMods().forEach(AdmittedModCatalog::captureHostGame);
        AdmittedModCatalog.freeze(selected.getMods());
        ConnectorMod.initialize(java.util.Objects.requireNonNull(bus), side == Dist.CLIENT);
    }
    @Override public synchronized void onLifecycle(LifecyclePhase phase) {
        if (!initialized) throw new IllegalStateException("Compatibility lifecycle before initialization");
        if (!phases.add(phase)) throw new IllegalStateException("Duplicate compatibility lifecycle: " + phase);
        if (phase == LifecyclePhase.CLIENT_SETUP) {
            if (dist != Dist.CLIENT) throw new IllegalStateException("Client lifecycle on dedicated server");
            ConnectorMod.onClientSetup();
            ConnectorModClient.onClientSetup();
        } else if (phase == LifecyclePhase.LOAD_COMPLETE && dist == Dist.CLIENT) {
            ConnectorModClient.onLoadComplete();
        }
    }
}
