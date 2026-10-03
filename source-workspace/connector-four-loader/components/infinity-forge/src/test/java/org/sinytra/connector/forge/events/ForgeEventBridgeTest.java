package org.sinytra.connector.forge.events;

import java.lang.reflect.Proxy;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import net.neoforged.bus.api.BusBuilder;
import net.neoforged.bus.api.Event;
import net.neoforged.bus.api.EventPriority;
import net.neoforged.bus.api.ICancellableEvent;
import net.neoforged.bus.api.IEventBus;
import org.sinytra.connector.forge.loader.ForgeEventBridge;

/** Uses the pinned host's real event bus; no Forge bus or game bootstrap. */
public final class ForgeEventBridgeTest {
    private static int checks;

    public static void main(String[] args) {
        suppliedBusPostsExactlyOnce();
        prioritiesPreserveIdentityAndMutablePayload();
        canceledListenersAreFiltered();
        uncanceledStateIsFinalResult();
        recanceledStateIsFinalResult();
        initiallyCanceledStateIsPreserved();
        listenerFailurePropagates(new IllegalStateException("original-listener-failure"));
        listenerFailurePropagates(new AssertionError("original-listener-error"));
        System.out.println("PASS: " + checks + " Forge event bridge/native bus checks (no game launch)");
    }

    private static void suppliedBusPostsExactlyOnce() {
        IEventBus owner = nativeBus();
        IEventBus unrelated = nativeBus();
        var calls = new AtomicInteger();
        var ownerDeliveries = new AtomicInteger();
        var unrelatedDeliveries = new AtomicInteger();
        var event = new ValueEvent(10);
        owner.addListener(ValueEvent.class, received -> {
            check(received == event, "native owner receives original event");
            ownerDeliveries.incrementAndGet();
            received.value += 5;
        });
        unrelated.addListener(ValueEvent.class, received -> unrelatedDeliveries.incrementAndGet());
        // Only the boundary call is counted here; all delivery is performed by the real bus.
        IEventBus supplied = (IEventBus) Proxy.newProxyInstance(IEventBus.class.getClassLoader(),
            new Class<?>[]{IEventBus.class}, (proxy, method, arguments) -> {
                check(method.getName().equals("post") && arguments.length == 1,
                    "bridge calls only one-argument native post");
                check(arguments[0] == event, "bridge does not substitute the event");
                calls.incrementAndGet();
                return owner.post((Event) arguments[0]);
            });
        check(!ForgeEventBridge.post(supplied, event), "plain custom event returns false");
        check(calls.get() == 1, "supplied bus post called exactly once");
        check(ownerDeliveries.get() == 1, "native owner delivers exactly once");
        check(unrelatedDeliveries.get() == 0, "unrelated bus has no delivery");
        check(event.value == 15, "caller observes original mutable payload");
    }

    private static void prioritiesPreserveIdentityAndMutablePayload() {
        IEventBus bus = nativeBus();
        var event = new RepairEvent(0);
        var order = new ArrayList<EventPriority>();
        EventPriority[] priorities = EventPriority.values();
        // Reverse registration ensures the assertion measures native priority sorting.
        for (int i = priorities.length - 1; i >= 0; i--) {
            EventPriority priority = priorities[i];
            bus.addListener(priority, RepairEvent.class, received -> {
                check(received == event, priority + " listener receives same object");
                check(received.repaired == priority.ordinal(), priority + " sees earlier mutations");
                received.repaired++;
                order.add(priority);
            });
        }
        check(!ForgeEventBridge.post(bus, event), "mutable repair event returns false");
        check(order.equals(List.of(priorities)), "native HIGHEST through LOWEST ordering once each");
        check(event.repaired == priorities.length, "all payload mutations are visible to caller");
    }

    private static void canceledListenersAreFiltered() {
        IEventBus bus = nativeBus();
        var event = new CancellableValueEvent();
        var order = new ArrayList<String>();
        bus.addListener(EventPriority.HIGHEST, CancellableValueEvent.class, received -> {
            check(received == event, "canceler receives original event");
            order.add("cancel");
            received.setCanceled(true);
        });
        bus.addListener(EventPriority.HIGH, false, CancellableValueEvent.class,
            received -> order.add("must-skip"));
        bus.addListener(EventPriority.NORMAL, true, CancellableValueEvent.class, received -> {
            check(received == event && received.isCanceled(), "receiveCanceled listener sees native canceled state");
            order.add("receive-canceled");
        });
        bus.addListener(EventPriority.LOW, CancellableValueEvent.class,
            received -> order.add("must-also-skip"));
        check(ForgeEventBridge.post(bus, event), "final canceled event returns true");
        check(order.equals(List.of("cancel", "receive-canceled")), "native cancellation filtering retained");
    }

    private static void uncanceledStateIsFinalResult() {
        IEventBus bus = nativeBus();
        var event = new CancellableValueEvent();
        var order = new ArrayList<String>();
        bus.addListener(EventPriority.HIGHEST, CancellableValueEvent.class, received -> {
            order.add("cancel");
            received.setCanceled(true);
        });
        bus.addListener(EventPriority.HIGH, CancellableValueEvent.class, received -> order.add("must-skip"));
        bus.addListener(EventPriority.NORMAL, true, CancellableValueEvent.class, received -> {
            check(received == event && received.isCanceled(), "uncanceler sees original canceled event");
            order.add("uncancel");
            received.setCanceled(false);
        });
        bus.addListener(EventPriority.LOWEST, false, CancellableValueEvent.class, received -> {
            check(received == event && !received.isCanceled(), "ordinary listener resumes after uncancellation");
            order.add("resumed");
        });
        check(!ForgeEventBridge.post(bus, event), "uncanceled final state returns false");
        check(order.equals(List.of("cancel", "uncancel", "resumed")), "native filtering reads live cancellation state");
        check(!event.isCanceled(), "bridge leaves final uncanceled state intact");
    }

    private static void recanceledStateIsFinalResult() {
        IEventBus bus = nativeBus();
        var event = new CancellableValueEvent();
        var order = new ArrayList<String>();
        bus.addListener(EventPriority.HIGHEST, CancellableValueEvent.class, received -> {
            order.add("cancel");
            received.setCanceled(true);
        });
        bus.addListener(EventPriority.HIGH, true, CancellableValueEvent.class, received -> {
            check(received.isCanceled(), "recancel flow starts canceled");
            order.add("uncancel");
            received.setCanceled(false);
        });
        bus.addListener(EventPriority.NORMAL, false, CancellableValueEvent.class, received -> {
            check(received == event && !received.isCanceled(), "ordinary recanceler sees uncanceled original event");
            order.add("recancel");
            received.setCanceled(true);
        });
        bus.addListener(EventPriority.LOW, CancellableValueEvent.class, received -> order.add("must-skip"));
        bus.addListener(EventPriority.LOWEST, true, CancellableValueEvent.class, received -> {
            check(received.isCanceled(), "last receiveCanceled listener sees recancellation");
            order.add("receive-recanceled");
        });
        check(ForgeEventBridge.post(bus, event), "recanceled final state returns true");
        check(order.equals(List.of("cancel", "uncancel", "recancel", "receive-recanceled")),
            "cancel/uncancel/recancel follows native priorities");
        check(event.isCanceled(), "bridge leaves final recanceled state intact");
    }

    private static void initiallyCanceledStateIsPreserved() {
        IEventBus bus = nativeBus();
        var event = new CancellableValueEvent();
        check(!ForgeEventBridge.post(bus, event), "listener-free cancellable event starts false");
        event.setCanceled(true);
        var deliveries = new AtomicInteger();
        bus.addListener(CancellableValueEvent.class, received -> {
            throw new AssertionError("ordinary listener received initially canceled event");
        });
        bus.addListener(true, CancellableValueEvent.class, received -> {
            check(received == event && received.isCanceled(), "initial cancellation passed unchanged to receiving listener");
            deliveries.incrementAndGet();
        });
        check(ForgeEventBridge.post(bus, event), "initially canceled event returns true");
        check(deliveries.get() == 1, "initially canceled event is dispatched once");
    }

    private static void listenerFailurePropagates(Throwable failure) {
        var event = new ValueEvent(0);
        var failureHandlers = new AtomicInteger();
        var deliveries = new AtomicInteger();
        IEventBus bus = BusBuilder.builder().setExceptionHandler((owner, received, listeners, index, thrown) -> {
            check(received == event, "native exception handler receives original event");
            check(thrown == failure, "native exception handler receives original throwable");
            check(index == 0, "native exception handler identifies failing listener");
            failureHandlers.incrementAndGet();
        }).build();
        bus.addListener(EventPriority.HIGHEST, ValueEvent.class, received -> {
            check(received == event, "failing listener receives original event");
            deliveries.incrementAndGet();
            received.value = 9;
            if (failure instanceof RuntimeException exception) throw exception;
            throw (Error) failure;
        });
        bus.addListener(EventPriority.LOWEST, ValueEvent.class, received -> {
            throw new AssertionError("listener ran after failed native dispatch");
        });
        Throwable observed = null;
        try {
            ForgeEventBridge.post(bus, event);
        } catch (Throwable thrown) {
            observed = thrown;
        }
        check(observed == failure, "bridge propagates original throwable without wrapping or swallowing");
        check(failureHandlers.get() == 1, "native exception handler runs once");
        check(deliveries.get() == 1, "failed dispatch is not retried");
        check(event.value == 9, "pre-exception native mutation remains on original event");
    }

    private static IEventBus nativeBus() {
        IEventBus bus = BusBuilder.builder().build();
        check(bus.getClass().getName().equals("net.neoforged.bus.EventBus"), "uses real native bus implementation");
        return bus;
    }

    private static void check(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
        checks++;
    }

    public static final class ValueEvent extends Event {
        public int value;
        public ValueEvent(int value) { this.value = value; }
    }

    public static final class RepairEvent extends Event {
        public int repaired;
        public RepairEvent(int repaired) { this.repaired = repaired; }
    }

    public static final class CancellableValueEvent extends Event implements ICancellableEvent {}
}
