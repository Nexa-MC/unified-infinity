package dev.unified.infinity.examples.fabric;

import net.fabricmc.fabric.api.event.Event;
import net.fabricmc.fabric.api.event.EventFactory;

/**
 * Equivalent ordered notification shape using genuine upstream Fabric types.
 * Compile-checked against the pinned Fabric API base JAR. This is not run by the
 * standalone test command: Fabric Event initialization needs Minecraft classes.
 */
public final class EquivalentFabricTick {
    public record Tick(long number) { }

    @FunctionalInterface
    public interface TickCallback {
        void onTick(Tick tick);
    }

    public static final Event<TickCallback> AFTER_TICK = EventFactory.createArrayBacked(
            TickCallback.class,
            tick -> { },
            listeners -> tick -> {
                for (TickCallback listener : listeners) listener.onTick(tick);
            });

    public static void installNewModListener() {
        AFTER_TICK.register(tick -> System.out.println("tick " + tick.number()));
    }

    public static void hostAfterTick(Tick tick) {
        AFTER_TICK.invoker().onTick(tick);
    }
}
