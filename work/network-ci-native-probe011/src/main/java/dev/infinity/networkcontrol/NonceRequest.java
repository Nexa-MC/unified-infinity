// SPDX-License-Identifier: MIT
package dev.infinity.networkcontrol;

import net.minecraft.network.RegistryFriendlyByteBuf;
import net.minecraft.network.codec.StreamCodec;
import net.minecraft.network.protocol.common.custom.CustomPacketPayload;
import net.minecraft.resources.ResourceLocation;

/** Exactly twelve bytes: a positive signed long followed by integer one. */
public record NonceRequest(long nonce, int sequence) implements CustomPacketPayload {
    public static final Type<NonceRequest> TYPE = new Type<>(
            ResourceLocation.fromNamespaceAndPath("network_control", "request"));
    public static final StreamCodec<RegistryFriendlyByteBuf, NonceRequest> STREAM_CODEC = new StreamCodec<>() {
        @Override
        public NonceRequest decode(RegistryFriendlyByteBuf buffer) {
            if (buffer.readableBytes() != 12) throw new IllegalArgumentException("request_size");
            return new NonceRequest(buffer.readLong(), buffer.readInt());
        }
        @Override
        public void encode(RegistryFriendlyByteBuf buffer, NonceRequest value) {
            buffer.writeLong(value.nonce());
            buffer.writeInt(value.sequence());
        }
    };
    public NonceRequest {
        if (nonce <= 0 || sequence != 1) throw new IllegalArgumentException("request_domain");
    }
    @Override
    public Type<NonceRequest> type() { return TYPE; }
}
