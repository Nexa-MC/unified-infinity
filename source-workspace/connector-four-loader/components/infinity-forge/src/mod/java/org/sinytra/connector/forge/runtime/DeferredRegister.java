package org.sinytra.connector.forge.runtime;

import java.util.Objects;
import java.util.function.Supplier;
import net.minecraft.core.Registry;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceKey;
import net.neoforged.bus.api.IEventBus;

/**
 * Bounded Forge ABI over the host's register. The delegate owns registry events,
 * supplier execution, registration order and the single host freeze schedule.
 */
public final class DeferredRegister<T> {
    private final net.neoforged.neoforge.registries.DeferredRegister<T> delegate;

    private DeferredRegister(ResourceKey<? extends Registry<T>> registryKey, String modId) {
        Objects.requireNonNull(registryKey);
        if (!registryKey.equals(Registries.BLOCK) && !registryKey.equals(Registries.ITEM)) {
            throw new UnsupportedOperationException("Forge 52 registry slice supports only minecraft:block and minecraft:item; got "
                + registryKey.location());
        }
        this.delegate = net.neoforged.neoforge.registries.DeferredRegister.create(registryKey, modId);
    }

    public static <T> DeferredRegister<T> create(ResourceKey<? extends Registry<T>> registryKey, String modId) {
        return new DeferredRegister<>(registryKey, modId);
    }

    public static <T> DeferredRegister<T> create(IForgeRegistry<T> registry, String modId) {
        return create(Objects.requireNonNull(registry).getRegistryKey(), modId);
    }

    public <I extends T> RegistryObject<I> register(String name, Supplier<? extends I> supplier) {
        // The supplier must remain lazy; constructing a facade never invokes it.
        return new RegistryObject<>(this.delegate.register(name, Objects.requireNonNull(supplier)));
    }

    public void register(IEventBus eventBus) {
        // The host rejects attaching this register twice, preventing double dispatch.
        this.delegate.register(Objects.requireNonNull(eventBus));
    }
}
