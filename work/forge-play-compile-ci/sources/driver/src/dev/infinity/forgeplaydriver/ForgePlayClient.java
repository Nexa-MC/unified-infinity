// SPDX-License-Identifier: MIT
package dev.infinity.forgeplaydriver;

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
import dev.infinity.forgeplayprobe.PlayProbe;


/** Loaded only on physical clients; the common registrar never names this class. */
@Mod(value = ForgePlayDriver.MOD_ID, dist = Dist.CLIENT)
public final class ForgePlayClient {
    private ForgePlayDriver.Input input;
    private Connection joined;
    private int sent;
    private int received;
    private long deadline;
    private boolean releasing;
    private boolean stopped;

    public ForgePlayClient(IEventBus modBus) { modBus.addListener(this::setup); }

    private void setup(FMLClientSetupEvent event) {
        event.enqueueWork(() -> {
            try {
                ForgePlayDriver.require(Minecraft.getInstance().isSameThread(), "client_wrong_thread");
                ForgePlayDriver.requireFresh();
                input = ForgePlayDriver.readInput();
                ForgePlayDriver.installClientReply(this::reply);
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
            ForgePlayDriver.require(minecraft.isSameThread(), "client_wrong_thread");
            ForgePlayDriver.require(!minecraft.hasSingleplayerServer(), "client_integrated_server");
            ForgePlayDriver.require(sent == 0 && joined == null, "client_duplicate_join");
            ForgePlayDriver.require(ForgePlayDriver.PLAYER_UUID.equals(event.getPlayer().getUUID())
                    && ForgePlayDriver.PLAYER_NAME.equals(event.getPlayer().getGameProfile().getName()), "client_wrong_identity");
            joined = event.getConnection();
            ForgePlayDriver.require(minecraft.getConnection() != null
                    && minecraft.getConnection().getConnection() == joined, "client_wrong_connection");
            ForgePlayDriver.requireRemote(joined, input.port(), true);
            sent = 1;
            deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(20);
            PlayProbe.send(joined, input.nonce());
        } catch (RuntimeException exception) { fail(exception, "client_join_failure"); }
    }

    private void reply(PlayProbe.Echo payload, Connection connection) {
        try {
            var minecraft = Minecraft.getInstance();
            ForgePlayDriver.require(!stopped && !ForgePlayDriver.hasFailed(ForgePlayDriver.Role.CLIENT), "client_already_failed");
            ForgePlayDriver.require(minecraft.isSameThread(), "client_wrong_thread");
            ForgePlayDriver.require(!minecraft.hasSingleplayerServer(), "client_integrated_server");
            ForgePlayDriver.require(connection.getPacketListener().protocol() == ConnectionProtocol.PLAY && connection.getReceiving() == PacketFlow.CLIENTBOUND,
                    "client_wrong_direction");
            ForgePlayDriver.require(sent == 1 && received == 0, "client_duplicate_or_unsolicited_reply");
            ForgePlayDriver.require(connection == joined, "client_wrong_connection");
            ForgePlayDriver.require(ForgePlayDriver.PLAYER_UUID.equals(minecraft.player.getUUID())
                    && ForgePlayDriver.PLAYER_NAME.equals(minecraft.player.getGameProfile().getName()), "client_wrong_identity");
            ForgePlayDriver.requireRemote(joined, input.port(), true);
            ForgePlayDriver.require(payload.value() == input.nonce() && payload.sequence() == 1 && payload.counter() == 1,
                    "client_reply_mismatch");
            received = 1;
            ForgePlayDriver.pass(ForgePlayDriver.Role.CLIENT, input.nonce(), input.port(), connection.getPacketListener().protocol(), connection.getReceiving());
            // Keep the real connection observable until the supervisor has captured its sockets.
            deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(15);
        } catch (RuntimeException exception) { fail(exception, "client_reply_failure"); }
    }

    private void tick(ClientTickEvent.Post event) {
        if (stopped) return;
        try {
            ForgePlayDriver.require(Minecraft.getInstance().isSameThread(), "client_wrong_thread");
            if (received == 1 && !releasing && ForgePlayDriver.releasePresent()) {
                ForgePlayDriver.requireRelease(input.nonce());
                releasing = true;
                joined.disconnect(Component.literal("forge_play_driver:complete"));
                Minecraft.getInstance().disconnect(new TitleScreen()); // Fires the real LoggingOut event.
            }
            if (!stopped && System.nanoTime() - deadline >= 0)
                throw new ForgePlayDriver.ProbeFailure(received == 1 ? "client_release_timeout"
                        : sent == 1 ? "client_reply_timeout" : "client_join_timeout");
        } catch (RuntimeException exception) { fail(exception, "client_tick_failure"); }
    }

    private void loggedOut(ClientPlayerNetworkEvent.LoggingOut event) {
        if (stopped || joined == null) return;
        try {
            ForgePlayDriver.require(Minecraft.getInstance().isSameThread(), "client_wrong_thread");
            ForgePlayDriver.require(releasing && sent == 1 && received == 1, "client_early_disconnect");
            ForgePlayDriver.require(event.getConnection() == joined && !joined.isConnected(), "client_disconnect_mismatch");
            ForgePlayDriver.disconnected(input.nonce());
            stopped = true;
            Minecraft.getInstance().stop();
        } catch (RuntimeException exception) { fail(exception, "client_logout_failure"); }
    }

    private void fail(RuntimeException exception, String fallback) {
        ForgePlayDriver.fail(ForgePlayDriver.Role.CLIENT, ForgePlayDriver.code(exception, fallback));
        stopped = true;
        var minecraft = Minecraft.getInstance();
        // A wrong-thread assertion is preserved above; cleanup is dispatched safely.
        minecraft.execute(() -> {
            if (joined != null && joined.isConnected()) joined.disconnect(Component.literal("forge_play_driver:failure"));
            minecraft.disconnect(new TitleScreen());
            minecraft.stop();
        });
    }
}
