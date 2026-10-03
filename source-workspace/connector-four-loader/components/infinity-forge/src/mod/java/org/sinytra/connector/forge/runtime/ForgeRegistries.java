package org.sinytra.connector.forge.runtime;

import net.minecraft.core.Registry;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceKey;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.item.Item;
import net.minecraft.world.level.block.Block;

/** Identity views of the host's vanilla registries; no registry is created or copied. */
public final class ForgeRegistries {
    public static final IForgeRegistry<Block> BLOCKS = new RegistryView<>(Registries.BLOCK);
    public static final IForgeRegistry<Item> ITEMS = new RegistryView<>(Registries.ITEM);

    private ForgeRegistries() {}

    private record RegistryView<T>(ResourceKey<Registry<T>> key) implements IForgeRegistry<T> {
        @Override
        public ResourceKey<Registry<T>> getRegistryKey() {
            return this.key;
        }

        @Override
        public ResourceLocation getRegistryName() {
            return this.key.location();
        }
    }
}
