package org.sinytra.connector.forge.runtime;

import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;
import net.minecraft.core.Registry;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceKey;
import net.minecraft.resources.ResourceLocation;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.neoforge.registries.DeferredHolder;

public final class ForgeRegistryFacadeTest {
    private static int checks;
    public static void main(String[] args) {
        var registryKey = ResourceKey.<String>createRegistryKey(ResourceLocation.fromNamespaceAndPath("test", "absent_registry"));
        var key = ResourceKey.create(registryKey, ResourceLocation.fromNamespaceAndPath("facade_test", "item"));
        var holder = new ControlledHolder(key);
        RegistryObject<String> object = new RegistryObject<>(holder);
        Supplier<String> stable = object;
        check(!object.isPresent(), "unbound object absent");
        check(object.getId().equals(key.location()), "id available before binding");
        check(object.getKey().equals(key), "key available before binding");
        try { object.get(); throw new AssertionError("premature get succeeded"); }
        catch (NullPointerException expected) { check(expected.getMessage().equals("Registry Object not present: facade_test:item"), "Forge premature get NPE and message"); }
        check(holder.getCalls == 0, "unbound host getter never invoked");
        holder.value = "registered value";
        check(object.isPresent(), "bound holder becomes present");
        check(object.get().equals("registered value"), "bound getter delegates");
        check(stable == object && stable.get().equals("registered value"), "stable supplier identity");
        check(ForgeRegistries.BLOCKS.getRegistryKey() == Registries.BLOCK, "block view shares vanilla registry key");
        check(ForgeRegistries.ITEMS.getRegistryKey() == Registries.ITEM, "item view shares vanilla registry key");
        check(ForgeRegistries.ITEMS.getRegistryName().equals(Registries.ITEM.location()), "view registry name");
        var keyed = DeferredRegister.create(Registries.ITEM, "facade_test");
        var viewed = DeferredRegister.create(ForgeRegistries.ITEMS, "facade_test");
        check(keyed != null && viewed != null, "both create overloads link");
        try { DeferredRegister.create(registryKey, "facade_test"); throw new AssertionError("custom registry accepted"); }
        catch (UnsupportedOperationException expected) { check(expected.getMessage().contains("minecraft:block and minecraft:item"), "out-of-slice registry rejected"); }
        AtomicInteger listeners = new AtomicInteger();
        IEventBus bus = (IEventBus) Proxy.newProxyInstance(IEventBus.class.getClassLoader(), new Class<?>[]{IEventBus.class}, (p,m,a) -> {
            if (m.getName().equals("addListener")) listeners.incrementAndGet();
            return null;
        });
        keyed.register(bus);
        check(listeners.get() == 2, "delegate owns the two native registry listeners");
        try { keyed.register(bus); throw new AssertionError("double bus registration accepted"); }
        catch (IllegalStateException expected) { check(listeners.get() == 2, "duplicate attach does not add listeners"); }
        System.out.println("PASS: " + checks + " Forge registry facade checks (controlled host holder, no game launch)");
    }
    private static void check(boolean condition, String label) { if (!condition) throw new AssertionError(label); checks++; }
    private static final class ControlledHolder extends DeferredHolder<String, String> {
        String value;
        int getCalls;
        ControlledHolder(ResourceKey<String> key) { super(key); }
        @Override protected Registry<String> getRegistry() { return null; }
        @Override public boolean isBound() { return value != null; }
        @Override public String get() {
            getCalls++;
            if (value == null) throw new IllegalStateException("host missing registry");
            return value;
        }
    }
}
