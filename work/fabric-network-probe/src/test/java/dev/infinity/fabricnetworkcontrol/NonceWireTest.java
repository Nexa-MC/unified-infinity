// SPDX-License-Identifier: MIT
package dev.infinity.fabricnetworkcontrol;
import java.nio.ByteBuffer;
import java.util.Arrays;
public final class NonceWireTest {
    static int assertions;
    static void check(boolean ok) { assertions++; if (!ok) throw new AssertionError(assertions); }
    static void reject(Runnable r) { try { r.run(); } catch (IllegalArgumentException e) { assertions++; return; } throw new AssertionError("accepted invalid wire"); }
    public static void main(String[] args) {
        for (long nonce : new long[]{1, 255, 256, 2147483648L, Long.MAX_VALUE}) {
            var req = new NonceWire.Request(nonce,1);
            var rep = new NonceWire.Reply(nonce,1,1);
            check(NonceWire.encode(req).length == 12);
            check(NonceWire.encode(rep).length == 16);
            check(NonceWire.request(NonceWire.encode(req)).equals(req));
            check(NonceWire.reply(NonceWire.encode(rep)).equals(rep));
            check(Arrays.equals(NonceWire.encode(req), ByteBuffer.allocate(12).putLong(nonce).putInt(1).array()));
            check(Arrays.equals(NonceWire.encode(rep), ByteBuffer.allocate(16).putLong(nonce).putInt(1).putInt(1).array()));
        }
        for (int size=0;size<=32;size++) {
            final int n=size;
            if (size!=12) reject(()->NonceWire.request(new byte[n]));
            if (size!=16) reject(()->NonceWire.reply(new byte[n]));
        }
        reject(()->NonceWire.request(null)); reject(()->NonceWire.reply(null));
        for (long n : new long[]{Long.MIN_VALUE,-1,0}) {
            reject(()->new NonceWire.Request(n,1)); reject(()->new NonceWire.Reply(n,1,1));
            reject(()->NonceWire.request(ByteBuffer.allocate(12).putLong(n).putInt(1).array()));
            reject(()->NonceWire.reply(ByteBuffer.allocate(16).putLong(n).putInt(1).putInt(1).array()));
        }
        for (int n : new int[]{Integer.MIN_VALUE,-1,0,2,Integer.MAX_VALUE}) {
            reject(()->new NonceWire.Request(1,n)); reject(()->new NonceWire.Reply(1,n,1));
            reject(()->new NonceWire.Reply(1,1,n));
            reject(()->NonceWire.request(ByteBuffer.allocate(12).putLong(1).putInt(n).array()));
            reject(()->NonceWire.reply(ByteBuffer.allocate(16).putLong(1).putInt(n).putInt(1).array()));
            reject(()->NonceWire.reply(ByteBuffer.allocate(16).putLong(1).putInt(1).putInt(n).array()));
        }
        System.out.println("ACTUAL_SHARED_NONCE_WIRE assertions="+assertions+" PASS");
    }
}
