package dev.unified.infinity.examples;

import dev.unified.infinity.api.Capability;
import dev.unified.infinity.api.Event;
import dev.unified.infinity.api.EventSource;
import dev.unified.infinity.api.ModScope;
import dev.unified.infinity.api.Subscription;
import java.util.Set;

/** Standalone host simulation, not a Minecraft hook or a loader integration. */
public final class InfinityTickExample {
    private static final Capability SERVER_TICK = new Capability("infinity:server_tick");
    public record Tick(long number) { }

    public static void main(String[] args) {
        // Host: bind on its actual dispatch thread and keep the source private.
        EventSource<Tick> source = EventSource.onCurrentThread("infinity:after_tick", SERVER_TICK);
        Event<Tick> afterTick = source.event();

        // Host creates and passes this session scope and event to the new mod.
        try (ModScope mod = ModScope.open("example", Set.of(SERVER_TICK))) {
            // New mod: one typed subscription, no callback interface/factory needed.
            Subscription temporary = afterTick.listen(mod, tick -> System.out.println("tick " + tick.number()));
            source.emit(new Tick(1)); // Host dispatch; payload allocation is the host's choice.
            temporary.close();
            source.emit(new Tick(2)); // No temporary callback.

            afterTick.listen(mod, tick -> System.out.println("session tick " + tick.number()));
            source.emit(new Tick(3));
        } // Host teardown closes all still-registered callbacks.

        source.emit(new Tick(4));
        if (afterTick.listenerCount() != 0) throw new AssertionError("session listeners leaked");
        System.out.println("session closed; listeners=" + afterTick.listenerCount());
    }
}
