package org.sinytra.connector.forge.loader;

import net.neoforged.bus.api.Event;
import net.neoforged.bus.api.ICancellableEvent;
import net.neoforged.bus.api.IEventBus;

/** Boolean post ABI for the explicitly supported Forge 52 event slice. */
public final class ForgeEventBridge {
    private ForgeEventBridge() {}

    /**
     * Dispatches the original event once through its supplied native owner, then
     * exposes the final cancellation state expected by a Forge boolean post.
     * Listener ordering, filtering and exceptions remain owned by the native bus.
     * This slice targets a running host-owned bus; Forge bus lifecycle, cancellation
     * annotations, result and phase APIs are not emulated. In particular, it does
     * not synthesize Forge's false return for an inactive native bus.
     */
    public static boolean post(IEventBus bus, Event event) {
        bus.post(event);
        return event instanceof ICancellableEvent cancellable && cancellable.isCanceled();
    }
}
