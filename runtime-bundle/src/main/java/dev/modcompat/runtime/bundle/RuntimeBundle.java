package dev.modcompat.runtime.bundle;

import net.neoforged.fml.ModList;
import net.neoforged.fml.common.Mod;

/**
 * Native NeoForge host for the unchanged, embedded Forgified Fabric API archive.
 * Transformation and Fabric entrypoint handling belong entirely to Sinytra
 * Connector. This constructor runs after discovery and does not load JARs.
 */
@Mod(RuntimeBundle.MOD_ID)
public final class RuntimeBundle {
    public static final String MOD_ID = "mod_compat_runtime";

    public RuntimeBundle() {
        ModList mods = ModList.get();
        require(mods, "connector");
        require(mods, "fabric_api");
        require(mods, "forgified_fabric_api");
        System.getLogger(RuntimeBundle.class.getName()).log(System.Logger.Level.INFO,
                "Unified Infinity bundle initialized: original Sinytra Connector "
                + "and internally bundled Forgified Fabric API discovered. "
                + "Per-mod Fabric compatibility must still be tested.");
    }

    private static void require(ModList mods, String id) {
        if (!mods.isLoaded(id)) {
            throw new IllegalStateException("Required upstream runtime mod not discovered: " + id);
        }
    }
}
