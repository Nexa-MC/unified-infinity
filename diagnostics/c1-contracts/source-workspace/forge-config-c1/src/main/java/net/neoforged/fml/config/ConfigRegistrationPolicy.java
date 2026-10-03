/* SPDX-License-Identifier: LGPL-2.1-only */
package net.neoforged.fml.config;

import net.neoforged.fml.ModContainer;
import net.neoforged.fml.event.config.ModConfigEvent;
import org.jetbrains.annotations.ApiStatus;

/** Internal registration semantics. The native tracker remains the sole IO/watch/lock owner. */
@ApiStatus.Internal
public interface ConfigRegistrationPolicy {
    ConfigRegistrationPolicy NATIVE = new ConfigRegistrationPolicy() {};

    static ConfigRegistrationPolicy of(ModConfig config) {
        return config.getSpec() instanceof ConfigRegistrationPolicy policy ? policy : NATIVE;
    }

    default boolean recoverReadFailure() { return true; }
    default boolean backupOnCorrection(boolean initialLoad) { return true; }
    default boolean validateCreatedFile() { return false; }
    default boolean notifyAfterSave() { return true; }
    default boolean saveAfterInitialLoad() { return false; }

    default void dispatchEvent(ModConfig config, ModContainer container, ModConfigEvent event) {
        container.acceptEvent(event);
    }

    /** Runs a facade's mutation and autosave under the existing per-mod owner lock. */
    static void mutateAndSave(ModConfig config, Runnable mutation, Runnable successfulCommit) {
        config.lock.lock();
        try {
            if (config.loadedConfig == null) throw new IllegalStateException("Config is not loaded: " + config.getFileName());
            mutation.run();
            config.loadedConfig.save();
            // Forge's synchronous autosave returns before ConfigValue commits its cache.
            // On write failure the raw mutation remains, but the old cache must survive.
            successfulCommit.run();
        } finally {
            config.lock.unlock();
        }
    }
}
