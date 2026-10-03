package dev.infinity.registryprobe;

import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.minecraft.class_1792;
import net.minecraft.class_2378;
import net.minecraft.class_2960;
import net.minecraft.class_7923;

/** Project-owned Fabric fixture using real, direct intermediary Minecraft bytecode. */
public final class RegistryProbe implements ModInitializer {
    private static final String ID = "infinity_registry_probe:test_item";

    @Override
    public void onInitialize() {
        class_2960 id = class_2960.method_60655("infinity_registry_probe", "test_item");
        class_1792 item = new class_1792(new class_1792.class_1793());
        class_1792 registered = class_2378.method_10230(class_7923.field_41178, id, item);
        if (registered != item || class_7923.field_41178.method_10223(id) != item) {
            throw new IllegalStateException("Registry lookup did not return the registered item");
        }
        System.out.println("INFINITY_REGISTRY_PROBE registration=PASS id=" + ID);
        ServerLifecycleEvents.SERVER_STARTED.register(server -> {
            if (class_7923.field_41178.method_10223(id) != item) {
                throw new IllegalStateException("Registered item identity changed before SERVER_STARTED");
            }
            System.out.println("INFINITY_REGISTRY_PROBE lifecycle=SERVER_STARTED registry=PASS id=" + ID);
        });
    }
}
