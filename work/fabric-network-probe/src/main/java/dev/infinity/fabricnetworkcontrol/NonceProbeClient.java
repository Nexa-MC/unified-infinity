// SPDX-License-Identifier: MIT
package dev.infinity.fabricnetworkcontrol;

import java.util.concurrent.TimeUnit;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.network.Connection;
import net.minecraft.network.ConnectionProtocol;
import net.minecraft.network.chat.Component;
import net.minecraft.network.protocol.PacketFlow;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.networking.v1.ClientPlayNetworking;
import net.fabricmc.fabric.api.client.networking.v1.ClientPlayConnectionEvents;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientLifecycleEvents;

/** Loaded only on physical clients; the common registrar never names this class. */
public final class NonceProbeClient implements ClientModInitializer {
    private NonceProbe.Input input;
    private Connection joined;
    private int sent;
    private int received;
    private long deadline;
    private boolean releasing;
    private boolean stopped;

    @Override
    public void onInitializeClient() {
        try {
            NonceProbe.require(ClientPlayNetworking.registerGlobalReceiver(NonceReply.TYPE, this::reply),
                    "client_receiver_duplicate");
            ClientPlayConnectionEvents.JOIN.register((handler, sender, client) -> joined(handler));
            ClientTickEvents.END_CLIENT_TICK.register(client -> tick());
            ClientPlayConnectionEvents.DISCONNECT.register((handler, client) -> loggedOut(handler));
            ClientLifecycleEvents.CLIENT_STARTED.register(client -> {
                try {
                    NonceProbe.require(client == Minecraft.getInstance() && client.isSameThread(), "client_wrong_thread");
                    NonceProbe.require(input == null, "client_setup_duplicate");
                    NonceProbe.requireFresh();
                    input = NonceProbe.readInput();
                    deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(90);
                } catch (RuntimeException exception) { fail(exception, "client_setup_failure"); }
            });
        } catch (RuntimeException exception) { fail(exception, "client_setup_failure"); }
    }

    private void joined(net.minecraft.client.multiplayer.ClientPacketListener handler) {
        try {
            var minecraft = Minecraft.getInstance();
            NonceProbe.require(minecraft.isSameThread(), "client_wrong_thread");
            NonceProbe.require(!minecraft.hasSingleplayerServer(), "client_integrated_server");
            NonceProbe.require(input != null, "client_setup_missing");
            NonceProbe.require(sent == 0 && joined == null, "client_duplicate_join");
            NonceProbe.require(NonceProbe.PLAYER_UUID.equals(minecraft.player.getUUID())
                    && NonceProbe.PLAYER_NAME.equals(minecraft.player.getGameProfile().getName()), "client_wrong_identity");
            joined = handler.getConnection();
            NonceProbe.require(minecraft.getConnection() != null
                    && minecraft.getConnection().getConnection() == joined, "client_wrong_connection");
            NonceProbe.requireRemote(joined, input.port(), true);
            sent = 1;
            deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(20);
            NonceProbe.require(ClientPlayNetworking.canSend(NonceRequest.TYPE), "client_channel_missing");
            ClientPlayNetworking.send(new NonceRequest(input.nonce(), 1));
        } catch (RuntimeException exception) { fail(exception, "client_join_failure"); }
    }

    private void reply(NonceReply payload, ClientPlayNetworking.Context context) {
        try {
            var minecraft = Minecraft.getInstance();
            NonceProbe.require(!stopped && !NonceProbe.hasFailed(NonceProbe.Role.CLIENT), "client_already_failed");
            NonceProbe.require(minecraft.isSameThread(), "client_wrong_thread");
            NonceProbe.require(!minecraft.hasSingleplayerServer(), "client_integrated_server");
            NonceProbe.require(context.client() == minecraft && minecraft.getConnection() != null,
                    "client_wrong_context");
            var handler = minecraft.getConnection();
            NonceProbe.require(handler.protocol() == ConnectionProtocol.PLAY && handler.flow() == PacketFlow.CLIENTBOUND,
                    "client_wrong_direction");
            NonceProbe.require(sent == 1 && received == 0, "client_duplicate_or_unsolicited_reply");
            NonceProbe.require(handler.getConnection() == joined, "client_wrong_connection");
            NonceProbe.require(NonceProbe.PLAYER_UUID.equals(context.player().getUUID())
                    && NonceProbe.PLAYER_NAME.equals(context.player().getGameProfile().getName()), "client_wrong_identity");
            NonceProbe.requireRemote(joined, input.port(), true);
            NonceProbe.require(payload.nonce() == input.nonce() && payload.sequence() == 1 && payload.counter() == 1,
                    "client_reply_mismatch");
            received = 1;
            NonceProbe.qualify(NonceProbe.Role.CLIENT, input.nonce());
            NonceProbe.pass(NonceProbe.Role.CLIENT, input.nonce(), input.port(), handler.protocol(), handler.flow());
            // Keep the real connection observable until the supervisor has captured its sockets.
            deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(15);
        } catch (RuntimeException exception) { fail(exception, "client_reply_failure"); }
    }

    private void tick() {
        if (stopped || input == null) return;
        try {
            NonceProbe.require(Minecraft.getInstance().isSameThread(), "client_wrong_thread");
            if (received == 1 && !releasing && NonceProbe.releasePresent()) {
                NonceProbe.requireRelease(input.nonce());
                releasing = true;
                joined.disconnect(Component.literal("network_control:complete"));
                Minecraft.getInstance().disconnect(new TitleScreen()); // Fires the actual Fabric DISCONNECT callback.
            }
            if (!stopped && System.nanoTime() - deadline >= 0)
                throw new NonceProbe.ProbeFailure(received == 1 ? "client_release_timeout"
                        : sent == 1 ? "client_reply_timeout" : "client_join_timeout");
        } catch (RuntimeException exception) { fail(exception, "client_tick_failure"); }
    }

    private void loggedOut(net.minecraft.client.multiplayer.ClientPacketListener handler) {
        if (stopped || joined == null) return;
        try {
            NonceProbe.require(Minecraft.getInstance().isSameThread(), "client_wrong_thread");
            NonceProbe.require(releasing && sent == 1 && received == 1, "client_early_disconnect");
            NonceProbe.require(handler.getConnection() == joined && !joined.isConnected(), "client_disconnect_mismatch");
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
