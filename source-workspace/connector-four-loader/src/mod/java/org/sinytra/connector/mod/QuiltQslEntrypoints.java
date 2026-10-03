package org.sinytra.connector.mod;

import org.sinytra.connector.quilt.QuiltBridge;

/** Linked only when the separately discovered original QSL base module has been admitted. */
final class QuiltQslEntrypoints {
    private QuiltQslEntrypoints() {}
    static void initialize() {
        QuiltBridge.invokeOnce("init", org.quiltmc.qsl.base.api.entrypoint.ModInitializer.class,
            org.quiltmc.qsl.base.api.entrypoint.ModInitializer::onInitialize);
    }
    static void initializeClient() {
        QuiltBridge.invokeOnce("client_init", org.quiltmc.qsl.base.api.entrypoint.client.ClientModInitializer.class,
            org.quiltmc.qsl.base.api.entrypoint.client.ClientModInitializer::onInitializeClient);
    }
    static void initializeServer() {
        QuiltBridge.invokeOnce("server_init", org.quiltmc.qsl.base.api.entrypoint.server.DedicatedServerModInitializer.class,
            org.quiltmc.qsl.base.api.entrypoint.server.DedicatedServerModInitializer::onInitializeServer);
    }
}
