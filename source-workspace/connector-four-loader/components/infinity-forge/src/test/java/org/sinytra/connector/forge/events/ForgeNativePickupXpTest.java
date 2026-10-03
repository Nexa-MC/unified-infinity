package org.sinytra.connector.forge.events;

import java.util.ArrayList;
import java.util.List;
import net.neoforged.bus.api.BusBuilder;
import net.neoforged.bus.api.EventPriority;
import net.neoforged.bus.api.ICancellableEvent;
import net.neoforged.neoforge.event.entity.player.PlayerXpEvent;
import org.sinytra.connector.forge.loader.ForgeEventBridge;

/** Exercises the actual native event with null payloads; never bootstraps Minecraft. */
public final class ForgeNativePickupXpTest {
    private static int checks;

    public static void main(String[] args) {
        var bus = BusBuilder.builder().build();
        var event = new PlayerXpEvent.PickupXp(null, null);
        check(event.getEntity() == null && event.getOrb() == null, "native constructor accepts null payloads");
        check(event instanceof ICancellableEvent, "native PickupXp owns cancellation contract");
        check(!ForgeEventBridge.post(bus, event), "uncanceled native PickupXp returns false");
        var order = new ArrayList<String>();
        bus.addListener(EventPriority.HIGHEST, PlayerXpEvent.PickupXp.class, received -> {
            check(received == event, "native PickupXp identity preserved");
            received.setCanceled(true);
            order.add("cancel");
        });
        bus.addListener(EventPriority.HIGH, false, PlayerXpEvent.PickupXp.class,
            received -> order.add("must-skip"));
        bus.addListener(EventPriority.NORMAL, true, PlayerXpEvent.PickupXp.class, received -> {
            check(received == event && received.isCanceled(), "receiving native listener sees same canceled PickupXp");
            order.add("receive-canceled");
        });
        check(ForgeEventBridge.post(bus, event), "canceled native PickupXp returns true");
        check(order.equals(List.of("cancel", "receive-canceled")), "native PickupXp cancellation filters listeners");
        check(event.isCanceled(), "native cancellation retained after bridge returns");
        check(event.getEntity() == null && event.getOrb() == null, "native payload references remain untouched");
        System.out.println("PASS: " + checks + " native NeoForge PickupXp bridge checks (null payloads, no game bootstrap)");
    }

    private static void check(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
        checks++;
    }
}
