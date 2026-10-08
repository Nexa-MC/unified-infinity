// SPDX-License-Identifier: MIT
package dev.infinity.networkcontrol;

import net.minecraft.network.RegistryFriendlyByteBuf;
import net.minecraft.network.codec.StreamCodec;
import net.minecraft.network.protocol.common.custom.CustomPacketPayload;
import net.minecraft.resources.ResourceLocation;

/** Exactly sixteen bytes; one is the only allowed authoritative counter value. */
public record NonceReply(long nonce, int sequence, int counter) implements CustomPacketPayload {
    public static final Type<NonceReply> TYPE = new Type<>(
            ResourceLocation.fromNamespaceAndPath("network_control", "reply"));
    public static final StreamCodec<RegistryFriendlyByteBuf, NonceReply> STREAM_CODEC = new StreamCodec<>() {
        @Override
        public NonceReply decode(RegistryFriendlyByteBuf buffer) {
            if (buffer.readableBytes() != 16) throw new IllegalArgumentException("reply_size");
            return new NonceReply(buffer.readLong(), buffer.readInt(), buffer.readInt());
        }
        @Override
        public void encode(RegistryFriendlyByteBuf buffer, NonceReply value) {
            buffer.writeLong(value.nonce());
            buffer.writeInt(value.sequence());
            buffer.writeInt(value.counter());
        }
    };
    public NonceReply {
        if (nonce <= 0 || sequence != 1 || counter != 1)
            throw new IllegalArgumentException("reply_domain");
    }
    @Override
    public Type<NonceReply> type() { return TYPE; }
}
