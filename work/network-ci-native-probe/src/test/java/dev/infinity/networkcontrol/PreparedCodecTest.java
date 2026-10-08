// SPDX-License-Identifier: MIT
package dev.infinity.networkcontrol;

import io.netty.buffer.Unpooled;
import java.util.HexFormat;
import net.minecraft.core.RegistryAccess;
import net.minecraft.network.ConnectionProtocol;
import net.minecraft.network.RegistryFriendlyByteBuf;
import net.minecraft.network.protocol.PacketFlow;

/** Prepared source only; no test JVM or game was launched during preparation. */
public final class PreparedCodecTest {
    private static int checked;
    private PreparedCodecTest() {}

    public static void main(String[] args) {
        for (long nonce : new long[] { 1L, 123456789L, Long.MAX_VALUE }) {
            var buffer = buffer();
            try {
                var request = new NonceRequest(nonce, 1);
                NonceRequest.STREAM_CODEC.encode(buffer, request);
                check(buffer.readableBytes() == 12);
                check(request.equals(NonceRequest.STREAM_CODEC.decode(buffer)));
                var reply = new NonceReply(nonce, 1, 1);
                NonceReply.STREAM_CODEC.encode(buffer, reply);
                check(buffer.readableBytes() == 16);
                check(reply.equals(NonceReply.STREAM_CODEC.decode(buffer)));
            } finally { buffer.release(); }
        }
        var buffer = buffer();
        try {
            NonceRequest.STREAM_CODEC.encode(buffer, new NonceRequest(1, 1));
            byte[] bytes = new byte[12];
            buffer.readBytes(bytes);
            check(HexFormat.of().formatHex(bytes).equals("000000000000000100000001"));
        } finally { buffer.release(); }
        reject(() -> new NonceRequest(0, 1));
        reject(() -> new NonceRequest(-1, 1));
        reject(() -> new NonceRequest(1, 0));
        reject(() -> new NonceRequest(1, 2));
        reject(() -> new NonceReply(0, 1, 1));
        reject(() -> new NonceReply(1, 2, 1));
        reject(() -> new NonceReply(1, 1, 0));
        reject(() -> new NonceReply(1, 1, 2));
        for (int length : new int[] { 0, 11, 13, 2048 }) {
            var invalid = buffer();
            try { invalid.writeZero(length); reject(() -> NonceRequest.STREAM_CODEC.decode(invalid)); }
            finally { invalid.release(); }
        }
        for (int length : new int[] { 0, 15, 17, 2048 }) {
            var invalid = buffer();
            try { invalid.writeZero(length); reject(() -> NonceReply.STREAM_CODEC.decode(invalid)); }
            finally { invalid.release(); }
        }
        check(NonceProbe.parseInput("{\"schema\":1,\"nonce\":1,\"sequence\":1,\"port\":25631}\n").nonce() == 1);
        check(NonceProbe.parseInput("{\"schema\":1,\"nonce\":9223372036854775807,\"sequence\":1,\"port\":25632}\n").port() == 25632);
        for (String invalid : new String[] {
                "{\"schema\":1,\"nonce\":0,\"sequence\":1,\"port\":25631}\n",
                "{\"schema\":1,\"nonce\":-1,\"sequence\":1,\"port\":25631}\n",
                "{\"schema\":1,\"nonce\":9223372036854775808,\"sequence\":1,\"port\":25631}\n",
                "{\"schema\":1,\"nonce\":1,\"sequence\":2,\"port\":25631}\n",
                "{\"schema\":1,\"nonce\":1,\"sequence\":1,\"port\":25565}\n",
                "{\"schema\":1,\"nonce\":1,\"sequence\":1,\"port\":25631,\"path\":\"/tmp/x\"}\n",
                "{\"schema\":1,\"nonce\":1,\"nonce\":2,\"sequence\":1,\"port\":25631}\n",
                "{\"schema\":1,\"nonce\":1,\"sequence\":1,\"port\":25631}",
                "{\"schema\":1,\"nonce\":1e0,\"sequence\":1,\"port\":25631}\n" }) {
            reject(() -> NonceProbe.parseInput(invalid));
        }
        check(NonceProbe.directionFields(NonceProbe.Role.SERVER, ConnectionProtocol.PLAY, PacketFlow.SERVERBOUND)
                .equals(",\"phase\":\"PLAY\",\"flow\":\"SERVERBOUND\""));
        check(NonceProbe.directionFields(NonceProbe.Role.CLIENT, ConnectionProtocol.PLAY, PacketFlow.CLIENTBOUND)
                .equals(",\"phase\":\"PLAY\",\"flow\":\"CLIENTBOUND\""));
        reject(() -> NonceProbe.directionFields(NonceProbe.Role.SERVER, ConnectionProtocol.PLAY, PacketFlow.CLIENTBOUND));
        reject(() -> NonceProbe.directionFields(NonceProbe.Role.CLIENT, ConnectionProtocol.PLAY, PacketFlow.SERVERBOUND));
        reject(() -> NonceProbe.directionFields(NonceProbe.Role.SERVER, ConnectionProtocol.CONFIGURATION, PacketFlow.SERVERBOUND));
        reject(() -> NonceProbe.directionFields(NonceProbe.Role.CLIENT, ConnectionProtocol.LOGIN, PacketFlow.CLIENTBOUND));
        System.out.println("Prepared codec/input checks: " + checked + "; no network or game acceptance");
    }
    private static RegistryFriendlyByteBuf buffer() {
        return new RegistryFriendlyByteBuf(Unpooled.buffer(), RegistryAccess.EMPTY);
    }
    private static void check(boolean value) {
        if (!value) throw new AssertionError("prepared_check");
        checked++;
    }
    private static void reject(Runnable operation) {
        try { operation.run(); }
        catch (IllegalArgumentException | NonceProbe.ProbeFailure expected) { checked++; return; }
        throw new AssertionError("expected_rejection");
    }
}
