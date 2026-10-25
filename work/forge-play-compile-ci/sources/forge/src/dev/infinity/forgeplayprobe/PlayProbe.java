// SPDX-License-Identifier: MIT
package dev.infinity.forgeplayprobe;

import java.util.Objects;
import net.minecraft.network.Connection;
import net.minecraft.network.ConnectionProtocol;
import net.minecraft.network.protocol.PacketFlow;
import net.minecraft.server.level.ServerPlayer;
import net.minecraftforge.event.network.CustomPayloadEvent;
import net.minecraftforge.network.ChannelBuilder;
import net.minecraftforge.network.SimpleChannel;

/** Original-Forge-compiled consumer. Native test driver observes, but never sends its own payload. */
public final class PlayProbe {
    private static final SimpleChannel CHANNEL = ChannelBuilder.named("unified_forge_play:nonce")
        .networkProtocolVersion(1).simpleChannel();
    private static volatile Observer observer;
    private static boolean registered;
    private PlayProbe() {}
    public record Nonce(long value, int sequence) {}
    public record Echo(long value, int sequence, int counter) {}
    public interface Observer {
        int serverNonce(Nonce nonce, Connection connection, ServerPlayer sender);
        void clientEcho(Echo echo, Connection connection);
        void failed(boolean server, Throwable failure);
    }
    public static synchronized void observe(Observer value) {
        if (observer != null) throw new IllegalStateException("duplicate observer");
        observer = Objects.requireNonNull(value);
    }
    public static synchronized void register() {
        if (registered) throw new IllegalStateException("duplicate registration");
        CHANNEL.messageBuilder(Nonce.class, 0).direction(PacketFlow.SERVERBOUND)
            .encoder((m,b) -> { b.writeLong(m.value()); b.writeInt(m.sequence()); })
            .decoder(b -> new Nonce(b.readLong(), b.readInt()))
            .consumerNetworkThread(PlayProbe::nonce).add();
        CHANNEL.messageBuilder(Echo.class, 1).direction(PacketFlow.CLIENTBOUND)
            .encoder((m,b) -> { b.writeLong(m.value()); b.writeInt(m.sequence()); b.writeInt(m.counter()); })
            .decoder(b -> new Echo(b.readLong(), b.readInt(), b.readInt()))
            .consumerNetworkThread(PlayProbe::echo).add();
        CHANNEL.build();
        registered = true;
    }
    public static void send(Connection connection, long value) {
        requirePlay(connection, PacketFlow.CLIENTBOUND);
        if (!registered || observer == null) throw new IllegalStateException("probe not initialized");
        CHANNEL.send(new Nonce(value, 1), connection);
    }
    private static void nonce(Nonce message, CustomPayloadEvent.Context context) {
        requirePlay(context.getConnection(), PacketFlow.SERVERBOUND);
        if (!context.isServerSide() || context.isClientSide() || context.getSender() == null)
            throw new IllegalStateException("not serverbound player context");
        Observer o = Objects.requireNonNull(observer, "observer");
        context.enqueueWork(() -> {
            try {
                int counter = o.serverNonce(message, context.getConnection(), context.getSender());
                CHANNEL.reply(new Echo(message.value(), message.sequence(), counter), context);
            } catch (RuntimeException failure) { o.failed(true, failure); throw failure; }
        }).exceptionally(failure -> { o.failed(true, failure); return null; });
        context.setPacketHandled(true);
    }
    private static void echo(Echo message, CustomPayloadEvent.Context context) {
        requirePlay(context.getConnection(), PacketFlow.CLIENTBOUND);
        if (!context.isClientSide() || context.isServerSide() || context.getSender() != null)
            throw new IllegalStateException("not clientbound context");
        Observer o = Objects.requireNonNull(observer, "observer");
        context.enqueueWork(() -> o.clientEcho(message, context.getConnection()))
            .exceptionally(failure -> { o.failed(false, failure); return null; });
        context.setPacketHandled(true);
    }
    private static void requirePlay(Connection connection, PacketFlow receiving) {
        if (connection.getPacketListener() == null ||
            connection.getPacketListener().protocol() != ConnectionProtocol.PLAY ||
            connection.getReceiving() != receiving)
            throw new IllegalStateException("wrong PLAY connection direction");
    }
}
