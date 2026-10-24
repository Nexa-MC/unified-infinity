// SPDX-License-Identifier: MIT
package dev.infinity.fabricnetworkcontrol;

import java.nio.ByteBuffer;

/** Shared, bounded wire implementation used by the real game StreamCodecs; no game/API stubs. */
public final class NonceWire {
    private NonceWire() {}
    public record Request(long nonce, int sequence) {
        public Request { if (nonce <= 0 || sequence != 1) throw new IllegalArgumentException("request_domain"); }
    }
    public record Reply(long nonce, int sequence, int counter) {
        public Reply { if (nonce <= 0 || sequence != 1 || counter != 1) throw new IllegalArgumentException("reply_domain"); }
    }
    public static Request request(byte[] bytes) {
        if (bytes == null || bytes.length != 12) throw new IllegalArgumentException("request_size");
        var b = ByteBuffer.wrap(bytes);
        return new Request(b.getLong(), b.getInt());
    }
    public static Reply reply(byte[] bytes) {
        if (bytes == null || bytes.length != 16) throw new IllegalArgumentException("reply_size");
        var b = ByteBuffer.wrap(bytes);
        return new Reply(b.getLong(), b.getInt(), b.getInt());
    }
    public static byte[] encode(Request value) {
        return ByteBuffer.allocate(12).putLong(value.nonce()).putInt(value.sequence()).array();
    }
    public static byte[] encode(Reply value) {
        return ByteBuffer.allocate(16).putLong(value.nonce()).putInt(value.sequence()).putInt(value.counter()).array();
    }
}
