package org.sinytra.connector.forge.runtime;

import net.minecraft.core.Registry;
import net.minecraft.resources.ResourceKey;
import net.minecraft.resources.ResourceLocation;

/**
 * Registry identity view used only by the admitted Forge MDK create overload.
 * This is not the full Forge registry contract. All other Forge member accesses
 * must be rejected by the symbol admission gate before loading a mod.
 */
public interface IForgeRegistry<T> {
    ResourceKey<Registry<T>> getRegistryKey();

    ResourceLocation getRegistryName();
}
