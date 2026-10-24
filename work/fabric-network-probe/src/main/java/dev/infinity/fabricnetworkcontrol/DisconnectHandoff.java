// SPDX-License-Identifier: MIT
package dev.infinity.fabricnetworkcontrol;

/** One retained observation, independent of Minecraft's discardable task queue.
 * Only the owner arms/finishes teardown and polls; callbacks only observe identities.
 * Every cross-thread field is guarded by this object. No game operation runs here.
 */
final class DisconnectHandoff {
    private Object client;
    private Object handler;
    private Object connection;
    private Object observed;
    private String failure;
    private boolean tearingDown;

    synchronized void beginTeardown(Object expectedClient, Object expectedHandler, Object expectedConnection) {
        checkFailure(); // An early notice must never be relabeled as a released disconnect.
        NonceProbe.require(connection == null && expectedClient != null
                && expectedHandler != null && expectedConnection != null, "client_disconnect_mismatch");
        client = expectedClient;
        handler = expectedHandler;
        connection = expectedConnection;
        tearingDown = true;
    }

    synchronized void observe(Object actualClient, Object actualHandler, Object actualConnection) {
        if (failure != null) return;
        if (connection == null) {
            failure = "client_early_disconnect";
        } else if (actualClient != client || actualHandler != handler || actualConnection != connection) {
            failure = "client_disconnect_mismatch";
        } else {
            // The pinned API can notify from both channelInactive and handleDisconnection.
            // Repeating exactly this identity is harmless; a conflicting notice stays fatal.
            observed = connection;
        }
    }

    synchronized boolean isTearingDown() { return tearingDown; }

    synchronized void finishTeardown() { tearingDown = false; }

    synchronized Object poll() {
        if (tearingDown) return null;
        checkFailure();
        return observed;
    }

    private void checkFailure() {
        if (failure != null) throw new NonceProbe.ProbeFailure(failure);
    }
}
