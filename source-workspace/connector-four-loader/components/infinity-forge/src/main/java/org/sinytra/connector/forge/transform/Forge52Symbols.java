package org.sinytra.connector.forge.transform;

import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.Handle;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.commons.MethodRemapper;
import org.objectweb.asm.commons.ClassRemapper;
import org.objectweb.asm.commons.Remapper;

/** An explicit Forge 52.1.0 Mojmap ABI slice, not a package-prefix relocation. */
public final class Forge52Symbols {
    public static final String ABI = "forge52-mojmap-slice-2-clumps-events";
    private static final String F = "net/minecraftforge/";
    private static final String R = "org/sinytra/connector/forge/runtime/";
    private static final String L = "org/sinytra/connector/forge/loader/";
    private static final String EVENT = F + "eventbus/api/Event";
    private static final String BUS = F + "eventbus/api/IEventBus";
    private static final String FORGE_POST = "(Lnet/minecraftforge/eventbus/api/Event;)Z";
    private static final String BRIDGE = L + "ForgeEventBridge";
    private static final String BRIDGE_POST = "(Lnet/neoforged/bus/api/IEventBus;Lnet/neoforged/bus/api/Event;)Z";
    private static final Map<String, String> TYPES = Map.ofEntries(
        Map.entry(F + "fml/common/Mod", L + "ForgeMod"),
        Map.entry(F + "fml/javafmlmod/FMLJavaModLoadingContext", L + "ForgeModLoadingContext"),
        Map.entry(EVENT, "net/neoforged/bus/api/Event"),
        Map.entry(F + "event/entity/player/PlayerXpEvent$PickupXp", "net/neoforged/neoforge/event/entity/player/PlayerXpEvent$PickupXp"),
        Map.entry(F + "eventbus/api/IEventBus", "net/neoforged/bus/api/IEventBus"),
        Map.entry(F + "common/MinecraftForge", "net/neoforged/neoforge/common/NeoForge"),
        Map.entry(F + "fml/event/lifecycle/FMLCommonSetupEvent", "net/neoforged/fml/event/lifecycle/FMLCommonSetupEvent"),
        Map.entry(F + "event/server/ServerStartedEvent", "net/neoforged/neoforge/event/server/ServerStartedEvent"),
        Map.entry(F + "event/TickEvent$ServerTickEvent$Post", "net/neoforged/neoforge/event/tick/ServerTickEvent$Post"),
        Map.entry(F + "registries/DeferredRegister", R + "DeferredRegister"),
        Map.entry(F + "registries/RegistryObject", R + "RegistryObject"),
        Map.entry(F + "registries/IForgeRegistry", R + "IForgeRegistry"),
        Map.entry(F + "registries/ForgeRegistries", R + "ForgeRegistries")
    );
    private static final Set<String> METHODS = Set.of(
        "fml/common/Mod.value()Ljava/lang/String;",
        "fml/javafmlmod/FMLJavaModLoadingContext.getModEventBus()Lnet/minecraftforge/eventbus/api/IEventBus;",
        "fml/javafmlmod/FMLJavaModLoadingContext.get()Lnet/minecraftforge/fml/javafmlmod/FMLJavaModLoadingContext;",
        "eventbus/api/Event.<init>()V",
        "event/entity/player/PlayerXpEvent$PickupXp.<init>(Lnet/minecraft/world/entity/player/Player;Lnet/minecraft/world/entity/ExperienceOrb;)V",
        "eventbus/api/IEventBus.post(Lnet/minecraftforge/eventbus/api/Event;)Z",
        "eventbus/api/IEventBus.addListener(Ljava/util/function/Consumer;)V",
        "fml/event/lifecycle/FMLCommonSetupEvent.enqueueWork(Ljava/lang/Runnable;)Ljava/util/concurrent/CompletableFuture;",
        "event/server/ServerStartedEvent.getServer()Lnet/minecraft/server/MinecraftServer;",
        "event/TickEvent$ServerTickEvent$Post.getServer()Lnet/minecraft/server/MinecraftServer;",
        "event/TickEvent$ServerTickEvent$Post.haveTime()Z",
        "registries/DeferredRegister.create(Lnet/minecraft/resources/ResourceKey;Ljava/lang/String;)Lnet/minecraftforge/registries/DeferredRegister;",
        "registries/DeferredRegister.create(Lnet/minecraftforge/registries/IForgeRegistry;Ljava/lang/String;)Lnet/minecraftforge/registries/DeferredRegister;",
        "registries/DeferredRegister.register(Ljava/lang/String;Ljava/util/function/Supplier;)Lnet/minecraftforge/registries/RegistryObject;",
        "registries/DeferredRegister.register(Lnet/minecraftforge/eventbus/api/IEventBus;)V",
        "registries/RegistryObject.get()Ljava/lang/Object;",
        "registries/RegistryObject.getId()Lnet/minecraft/resources/ResourceLocation;",
        "registries/RegistryObject.getKey()Lnet/minecraft/resources/ResourceKey;",
        "registries/RegistryObject.isPresent()Z",
        "registries/IForgeRegistry.getRegistryKey()Lnet/minecraft/resources/ResourceKey;",
        "registries/IForgeRegistry.getRegistryName()Lnet/minecraft/resources/ResourceLocation;"
    );
    private static final Set<String> FIELDS = Set.of(
        "common/MinecraftForge.EVENT_BUS:Lnet/minecraftforge/eventbus/api/IEventBus;",
        "registries/ForgeRegistries.ITEMS:Lnet/minecraftforge/registries/IForgeRegistry;",
        "registries/ForgeRegistries.BLOCKS:Lnet/minecraftforge/registries/IForgeRegistry;"
    );

    private Forge52Symbols() {}

    public static byte[] transform(byte[] input, Set<String> audit) {
        return transform(input, audit, Set.of());
    }

    public static byte[] transform(byte[] input, Set<String> audit, Set<String> eventSubclasses) {
        ClassReader reader = new ClassReader(input);
        Set<String> knownEventSubclasses = new java.util.HashSet<>(eventSubclasses);
        if (EVENT.equals(reader.getSuperName())) knownEventSubclasses.add(reader.getClassName());
        if (reader.getClassName().startsWith(F)) throw unsupported("bundled Forge implementation " + reader.getClassName());
        if (reader.getSuperName() != null && reader.getSuperName().startsWith(F) && !reader.getSuperName().equals(EVENT))
            throw unsupported("Forge API subclass " + reader.getClassName() + " extends " + reader.getSuperName());
        for (String iface : reader.getInterfaces()) if (iface.startsWith(F))
            throw unsupported("Forge API implementation " + reader.getClassName() + " implements " + iface);
        if (reader.readUnsignedShort(6) > 65) throw unsupported("class newer than Java 21: " + reader.getClassName());
        ClassWriter output = new ClassWriter(0);
        Remapper remapper = new Remapper() {
            @Override public String map(String name) {
                if (!name.startsWith(F)) return name;
                String mapped = TYPES.get(name);
                if (mapped == null) throw unsupported("type " + name);
                audit.add("TYPE " + name + " -> " + mapped);
                return mapped;
            }
            @Override public String mapMethodName(String owner, String name, String descriptor) {
                rejectSrg(owner, name);
                if (knownEventSubclasses.contains(owner) && Set.of("isCancelable", "isCanceled", "setCanceled", "hasResult",
                    "getResult", "setResult", "getListenerList", "getPhase", "setPhase").contains(name))
                    throw unsupported("unimplemented inherited Forge Event API " + owner + "." + name + descriptor);
                if (!owner.startsWith(F)) return name;
                String symbol = owner.substring(F.length()) + "." + name + descriptor;
                if (!METHODS.contains(symbol)) throw unsupported("method " + owner + "." + name + descriptor);
                String mapped = name.equals("haveTime") ? "hasTime" : name;
                audit.add("METHOD " + owner + "." + name + descriptor + " -> " + map(owner) + "." + mapped + mapMethodDesc(descriptor));
                return mapped;
            }
            @Override public String mapFieldName(String owner, String name, String descriptor) {
                rejectSrg(owner, name);
                if (!owner.startsWith(F)) return name;
                String symbol = owner.substring(F.length()) + "." + name + ":" + descriptor;
                if (!FIELDS.contains(symbol)) throw unsupported("field " + owner + "." + name + ":" + descriptor);
                audit.add("FIELD " + owner + "." + name + ":" + descriptor + " -> " + map(owner) + "." + name + ":" + mapDesc(descriptor));
                return name;
            }
            @Override public Object mapValue(Object value) {
                if (value instanceof String text) {
                    if (text.contains("net.minecraftforge.") || text.contains(F))
                        throw unsupported("reflective Forge string " + text);
                    if (text.matches(".*(?<![A-Za-z0-9_$])(?:[mf]_[0-9]+_|(?:method|field|class)_[0-9]+)(?![A-Za-z0-9_$]).*"))
                        throw unsupported("non-Mojmap symbolic string " + text);
                }
                if (value instanceof Handle handle && isPost(handle.getOwner(), handle.getName(), handle.getDesc())) {
                    if (handle.getTag() != Opcodes.H_INVOKEINTERFACE || !handle.isInterface())
                        throw unsupported("invalid Forge post handle " + handle);
                    audit.add("SEMANTIC_HANDLE Forge boolean post -> native owner dispatch " + BRIDGE + ".post" + BRIDGE_POST);
                    return new Handle(Opcodes.H_INVOKESTATIC, BRIDGE, "post", BRIDGE_POST, false);
                }
                return super.mapValue(value);
            }
        };
        ClassVisitor visitor = new ClassRemapper(output, remapper) {
            @Override protected MethodVisitor createMethodRemapper(MethodVisitor visitor) {
                return new MethodRemapper(visitor, remapper) {
                    @Override public void visitTypeInsn(int opcode, String type) {
                        if (opcode == Opcodes.NEW && type.equals(EVENT))
                            throw unsupported("direct Forge Event construction; native Event is abstract");
                        super.visitTypeInsn(opcode, type);
                    }
                    @Override public void visitMethodInsn(int opcode, String owner, String name, String descriptor, boolean isInterface) {
                        if (isPost(owner, name, descriptor)) {
                            if (opcode != Opcodes.INVOKEINTERFACE || !isInterface)
                                throw unsupported("invalid Forge post invocation opcode " + opcode);
                            audit.add("SEMANTIC_METHOD Forge boolean post -> native owner dispatch " + BRIDGE + ".post" + BRIDGE_POST);
                            mv.visitMethodInsn(Opcodes.INVOKESTATIC, BRIDGE, "post", BRIDGE_POST, false);
                        } else super.visitMethodInsn(opcode, owner, name, descriptor, isInterface);
                    }
                };
            }
            @Override public void visitInnerClass(String name, String outer, String inner, int access) {
                // javac records the old TickEvent outer hierarchy for a Post-only use.
                // These are descriptive attributes, not usable class symbols. Never map
                // the unsupported TickEvent base to a semantically different Neo event.
                if (name.startsWith(F)) {
                    audit.add("INNER_CLASS_METADATA omitted " + name);
                    return;
                }
                super.visitInnerClass(name, outer, inner, access);
            }
        };
        reader.accept(visitor, 0);
        return output.toByteArray();
    }

    private static boolean isPost(String owner, String name, String descriptor) {
        return owner.equals(BUS) && name.equals("post") && descriptor.equals(FORGE_POST);
    }

    private static void rejectSrg(String owner, String name) {
        if (owner.startsWith("net/minecraft/") && name.matches("[mf]_[0-9]+_"))
            throw unsupported("SRG member in Mojmap profile " + owner + "." + name);
    }

    public static IllegalArgumentException unsupported(String detail) {
        return new IllegalArgumentException("Unsupported Forge 52.1.0 ABI slice: " + detail);
    }

    /** Stable complete rule inventory, hashed into the derived cache identity. */
    public static String rules() {
        Set<String> result = new TreeSet<>();
        TYPES.forEach((from, to) -> result.add("TYPE " + from + " -> " + to));
        METHODS.forEach(s -> result.add("METHOD " + s));
        FIELDS.forEach(s -> result.add("FIELD " + s));
        result.add("haveTime()Z -> hasTime()Z");
        result.add("Forge IEventBus.post(Event):boolean -> static ForgeEventBridge.post(nativeBus,nativeEvent):boolean; handles and invokes");
        result.add("plain Event subclass+constructor only; @Cancelable, HasResult and remaining event methods unsupported");
        result.add("omit Forge InnerClasses metadata; reject other API subclasses, interfaces and reflective strings");
        return ABI + "\n" + String.join("\n", result) + "\n";
    }
}
