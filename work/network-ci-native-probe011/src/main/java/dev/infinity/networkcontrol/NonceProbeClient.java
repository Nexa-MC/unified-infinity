// SPDX-License-Identifier: MIT
package dev.infinity.networkcontrol;

import java.util.concurrent.TimeUnit;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.network.Connection;
import net.minecraft.network.ConnectionProtocol;
import net.minecraft.network.chat.Component;
import net.minecraft.network.protocol.PacketFlow;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.common.Mod;
import net.neoforged.fml.event.lifecycle.FMLClientSetupEvent;
import net.neoforged.neoforge.client.event.ClientPlayerNetworkEvent;
import net.neoforged.neoforge.client.event.ClientTickEvent;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.network.PacketDistributor;
import net.neoforged.neoforge.network.handling.IPayloadContext;

/** Loaded only on physical clients; the common registrar never names this class. */
@Mod(value = NonceProbe.MOD_ID, dist = Dist.CLIENT)
public final class NonceProbeClient {
    private NonceProbe.Input input;
    private Connection joined;
    private int sent;
    private int received;
    private long deadline;
    private boolean releasing;
    private boolean stopped;

    public NonceProbeClient(IEventBus modBus) { modBus.addListener(this::setup); }

    private void setup(FMLClientSetupEvent event) {
        event.enqueueWork(() -> {
            try {
                NonceProbe.require(Minecraft.getInstance().isSameThread(), "client_wrong_thread");
                NonceProbe.requireFresh();
                input = NonceProbe.readInput();
                NonceProbe.installClientReply(this::reply);
                NeoForge.EVENT_BUS.addListener(this::joined);
                NeoForge.EVENT_BUS.addListener(this::tick);
                NeoForge.EVENT_BUS.addListener(this::loggedOut);
                deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(90);
            } catch (RuntimeException exception) { fail(exception, "client_setup_failure"); }
        });
    }

    private void joined(ClientPlayerNetworkEvent.LoggingIn event) {
        try {
            var minecraft = Minecraft.getInstance();
            NonceProbe.require(minecraft.isSameThread(), "client_wrong_thread");
            NonceProbe.require(!minecraft.hasSingleplayerServer(), "client_integrated_server");
            NonceProbe.require(sent == 0 && joined == null, "client_duplicate_join");
            NonceProbe.require(NonceProbe.PLAYER_UUID.equals(event.getPlayer().getUUID())
                    && NonceProbe.PLAYER_NAME.equals(event.getPlayer().getGameProfile().getName()), "client_wrong_identity");
            joined = event.getConnection();
            NonceProbe.require(minecraft.getConnection() != null
                    && minecraft.getConnection().getConnection() == joined, "client_wrong_connection");
            NonceProbe.requireRemote(joined, input.port(), true);
            sent = 1;
            deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(20);
            PacketDistributor.sendToServer(new NonceRequest(input.nonce(), 1));
        } catch (RuntimeException exception) { fail(exception, "client_join_failure"); }
    }

    private void reply(NonceReply payload, IPayloadContext context) {
        try {
            var minecraft = Minecraft.getInstance();
            NonceProbe.require(!stopped && !NonceProbe.hasFailed(NonceProbe.Role.CLIENT), "client_already_failed");
            NonceProbe.require(minecraft.isSameThread(), "client_wrong_thread");
            NonceProbe.require(!minecraft.hasSingleplayerServer(), "client_integrated_server");
            NonceProbe.require(context.protocol() == ConnectionProtocol.PLAY && context.flow() == PacketFlow.CLIENTBOUND,
                    "client_wrong_direction");
            NonceProbe.require(sent == 1 && received == 0, "client_duplicate_or_unsolicited_reply");
            NonceProbe.require(context.connection() == joined, "client_wrong_connection");
            NonceProbe.require(NonceProbe.PLAYER_UUID.equals(context.player().getUUID())
                    && NonceProbe.PLAYER_NAME.equals(context.player().getGameProfile().getName()), "client_wrong_identity");
            NonceProbe.requireRemote(joined, input.port(), true);
            NonceProbe.require(payload.nonce() == input.nonce() && payload.sequence() == 1 && payload.counter() == 1,
                    "client_reply_mismatch");
            received = 1;
            NonceProbe.pass(NonceProbe.Role.CLIENT, input.nonce(), input.port(), context.protocol(), context.flow());
            // Keep the real connection observable until the supervisor has captured its sockets.
            deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(15);
        } catch (RuntimeException exception) { fail(exception, "client_reply_failure"); }
    }

    private void tick(ClientTickEvent.Post event) {
        if (stopped) return;
        try {
            NonceProbe.require(Minecraft.getInstance().isSameThread(), "client_wrong_thread");
            if (received == 1 && !releasing && NonceProbe.releasePresent()) {
                NonceProbe.requireRelease(input.nonce());
                releasing = true;
                joined.disconnect(Component.literal("network_control:complete"));
                Minecraft.getInstance().disconnect(new TitleScreen()); // Fires the real LoggingOut event.
            }
            if (!stopped && System.nanoTime() - deadline >= 0)
                throw new NonceProbe.ProbeFailure(received == 1 ? "client_release_timeout"
                        : sent == 1 ? "client_reply_timeout" : "client_join_timeout");
        } catch (RuntimeException exception) { fail(exception, "client_tick_failure"); }
    }

    private void loggedOut(ClientPlayerNetworkEvent.LoggingOut event) {
        if (stopped || joined == null) return;
        try {
            NonceProbe.require(Minecraft.getInstance().isSameThread(), "client_wrong_thread");
            NonceProbe.require(releasing && sent == 1 && received == 1, "client_early_disconnect");
            NonceProbe.require(event.getConnection() == joined && !joined.isConnected(), "client_disconnect_mismatch");
            NonceProbe.disconnected(input.nonce());
            stopped = true;
            Minecraft.getInstance().stop();
        } catch (RuntimeException exception) { fail(exception, "client_logout_failure"); }
    }

    private void fail(RuntimeException exception, String fallback) {
        NonceProbe.fail(NonceProbe.Role.CLIENT, NonceProbe.code(exception, fallback));
        stopped = true;
        var minecraft = Minecraft.getInstance();
        // A wrong-thread assertion is preserved above; cleanup is dispatched safely.
        minecraft.execute(() -> {
            if (joined != null && joined.isConnected()) joined.disconnect(Component.literal("network_control:failure"));
            minecraft.disconnect(new TitleScreen());
            minecraft.stop();
        });
    }
}
