// SPDX-License-Identifier: MIT
package dev.infinity.fabricnetworkcontrol;

import net.minecraft.network.RegistryFriendlyByteBuf;
import net.minecraft.network.codec.StreamCodec;
import net.minecraft.network.protocol.common.custom.CustomPacketPayload;
import net.minecraft.resources.ResourceLocation;

/** Exactly twelve bytes: a positive signed long followed by integer one. */
public record NonceRequest(long nonce, int sequence) implements CustomPacketPayload {
    public static final Type<NonceRequest> TYPE = new Type<>(
            ResourceLocation.fromNamespaceAndPath("fabric_network_control", "request"));
    public static final StreamCodec<RegistryFriendlyByteBuf, NonceRequest> STREAM_CODEC = new StreamCodec<>() {
        @Override
        public NonceRequest decode(RegistryFriendlyByteBuf buffer) {
            if (buffer.readableBytes() != 12) throw new IllegalArgumentException("request_size");
            byte[] bytes = new byte[12];
            buffer.readBytes(bytes);
            var value = NonceWire.request(bytes);
            return new NonceRequest(value.nonce(), value.sequence());
        }
        @Override
        public void encode(RegistryFriendlyByteBuf buffer, NonceRequest value) {
            buffer.writeBytes(NonceWire.encode(new NonceWire.Request(value.nonce(), value.sequence())));
        }
    };
    public NonceRequest {
        new NonceWire.Request(nonce, sequence);
    }
    @Override
    public Type<NonceRequest> type() { return TYPE; }
}
