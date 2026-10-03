package dev.modcompat.runtime.bundle;

import dev.modcompat.runtime.modlist.UnifiedModListEvents;
import java.util.EnumSet;
import java.util.Objects;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.ModList;
import net.neoforged.fml.loading.unified.GameCompatibilityComponent;

/**
 * Installation-pinned product GAME component owned by FML.
 * This is not an ordinary mod entrypoint or a public mod-author API. FML validates
 * its exact origin before construction and calls it after installing the final ModList.
 */
public final class RuntimeBundle implements GameCompatibilityComponent {
    private final EnumSet<LifecyclePhase> phases = EnumSet.noneOf(LifecyclePhase.class);
    private Dist dist;
    private boolean initialized;

    /** Construction alone has no discovery, validation, event-registration or client side effects. */
    public RuntimeBundle() { }

    @Override public synchronized void initialize(IEventBus internalBus, Dist side) {
        if (initialized) throw new IllegalStateException("Unified product GAME component initialized twice");
        Objects.requireNonNull(internalBus, "FML internal component event bus");
        dist = Objects.requireNonNull(side, "physical side");
        ModList mods = Objects.requireNonNull(ModList.get(), "Final host ModList must be installed before product initialization");
        require(mods, "fabric_api");
        require(mods, "forgified_fabric_api");
        // Core compatibility ownership is FML's pinned component contract, never a fake connector ModContainer.
        initialized = true;
        System.getLogger(RuntimeBundle.class.getName()).log(System.Logger.Level.INFO,
            "Unified Infinity internal product initialized: upstream Forgified Fabric API providers remain loaded; "
                + "source-owned compatibility lifecycle is managed by FML.");
    }

    @Override public synchronized void onLifecycle(LifecyclePhase phase) {
        if (!initialized) throw new IllegalStateException("Product lifecycle before FML initialization");
        Objects.requireNonNull(phase, "lifecycle phase");
        if (!phases.add(phase)) throw new IllegalStateException("Duplicate product lifecycle: " + phase);
        if (phase == LifecyclePhase.CLIENT_SETUP) {
            if (dist != Dist.CLIENT) throw new IllegalStateException("Client product lifecycle on dedicated server");
            // Direct, typed call inside the side guard. No class-name property, service lookup or reflection route.
            UnifiedModListEvents.initialize();
        } else if (phase == LifecyclePhase.DEDICATED_SERVER_SETUP && dist != Dist.DEDICATED_SERVER) {
            throw new IllegalStateException("Dedicated-server product lifecycle on client");
        }
    }

    private static void require(ModList mods, String id) {
        if (!mods.isLoaded(id)) throw new IllegalStateException("Required upstream API provider not selected: " + id);
    }
}
