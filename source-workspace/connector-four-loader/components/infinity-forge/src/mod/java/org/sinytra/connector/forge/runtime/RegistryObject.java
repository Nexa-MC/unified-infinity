package org.sinytra.connector.forge.runtime;

import java.util.Objects;
import java.util.function.Supplier;
import net.minecraft.resources.ResourceKey;
import net.minecraft.resources.ResourceLocation;
import net.neoforged.neoforge.registries.DeferredHolder;

/** Stable Supplier facade; intentionally does not expose the host Holder API. */
public final class RegistryObject<T> implements Supplier<T> {
    private final DeferredHolder<? super T, T> delegate;

    RegistryObject(DeferredHolder<? super T, T> delegate) {
        this.delegate = Objects.requireNonNull(delegate);
    }

    @Override
    public T get() {
        // Forge specifies NPE for an unavailable entry, even when a Neo holder
        // would throw IllegalStateException because its registry is unavailable.
        if (!isPresent()) {
            throw new NullPointerException("Registry Object not present: " + getId());
        }
        return this.delegate.get();
    }

    public ResourceLocation getId() {
        return this.delegate.getId();
    }

    @SuppressWarnings("unchecked")
    public ResourceKey<T> getKey() {
        // Forge narrows a registry's element key to the registered subtype.
        return (ResourceKey<T>) this.delegate.getKey();
    }

    public boolean isPresent() {
        return this.delegate.isBound();
    }
}
