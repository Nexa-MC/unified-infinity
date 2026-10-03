package org.sinytra.connector.forge.loader;

import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.ModLoadingContext;

/**
 * Per-mod facade for the admitted Forge constructor/context ABI.
 * This deliberately does not inherit Forge or Neo's different context APIs.
 */
public final class ForgeModLoadingContext {
    private final ForgeModContainer container;

    ForgeModLoadingContext(ForgeModContainer container) {
        this.container = container;
    }

    public IEventBus getModEventBus() {
        return this.container.getEventBus();
    }

    public void registerConfig(org.sinytra.connector.forge.config.ForgeModConfig.Type type,
                               org.sinytra.connector.forge.config.IForgeConfigSpec<?> spec) {
        registerConfig(type, spec, null);
    }

    public void registerConfig(org.sinytra.connector.forge.config.ForgeModConfig.Type type,
                               org.sinytra.connector.forge.config.IForgeConfigSpec<?> spec, String fileName) {
        org.sinytra.connector.forge.config.ForgeConfigSpecAdapter.register(
            net.neoforged.fml.config.ConfigTracker.INSTANCE, container, type, spec, fileName);
    }

    /** Resolves through the host's scope; there is no second active-mod context. */
    public static ForgeModLoadingContext get() {
        var active = ModLoadingContext.get().getActiveContainer();
        if (active instanceof ForgeModContainer forge) {
            return forge.context();
        }
        throw new IllegalStateException("Forge 52 loading context is only available while a Forge adapter mod is active");
    }
}
