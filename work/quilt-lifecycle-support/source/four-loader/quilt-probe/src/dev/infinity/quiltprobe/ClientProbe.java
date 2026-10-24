package dev.infinity.quiltprobe;
import org.quiltmc.loader.api.ModContainer;
import org.quiltmc.loader.api.minecraft.ClientOnly;
import org.quiltmc.qsl.base.api.entrypoint.client.ClientModInitializer;
@ClientOnly
public final class ClientProbe implements ClientModInitializer {
    private static int count;
    @Override public void onInitializeClient(ModContainer mod) {
        QuiltProbe.require(++count == 1, "client_init_once");
        QuiltProbe.pass("client_init", "count=1");
    }
}
