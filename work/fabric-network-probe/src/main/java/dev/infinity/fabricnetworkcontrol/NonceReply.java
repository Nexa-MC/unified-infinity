// SPDX-License-Identifier: MIT
package dev.infinity.fabricnetworkcontrol;

import net.minecraft.network.RegistryFriendlyByteBuf;
import net.minecraft.network.codec.StreamCodec;
import net.minecraft.network.protocol.common.custom.CustomPacketPayload;
import net.minecraft.resources.ResourceLocation;

/** Exactly sixteen bytes; one is the only allowed authoritative counter value. */
public record NonceReply(long nonce, int sequence, int counter) implements CustomPacketPayload {
    public static final Type<NonceReply> TYPE = new Type<>(
            ResourceLocation.fromNamespaceAndPath("fabric_network_control", "reply"));
    public static final StreamCodec<RegistryFriendlyByteBuf, NonceReply> STREAM_CODEC = new StreamCodec<>() {
        @Override
        public NonceReply decode(RegistryFriendlyByteBuf buffer) {
            if (buffer.readableBytes() != 16) throw new IllegalArgumentException("reply_size");
            byte[] bytes = new byte[16];
            buffer.readBytes(bytes);
            var value = NonceWire.reply(bytes);
            return new NonceReply(value.nonce(), value.sequence(), value.counter());
        }
        @Override
        public void encode(RegistryFriendlyByteBuf buffer, NonceReply value) {
            buffer.writeBytes(NonceWire.encode(new NonceWire.Reply(value.nonce(), value.sequence(), value.counter())));
        }
    };
    public NonceReply {
        new NonceWire.Reply(nonce, sequence, counter);
    }
    @Override
    public Type<NonceReply> type() { return TYPE; }
}
