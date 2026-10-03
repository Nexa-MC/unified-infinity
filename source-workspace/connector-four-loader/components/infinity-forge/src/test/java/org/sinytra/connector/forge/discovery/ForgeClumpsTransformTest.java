package org.sinytra.connector.forge.discovery;

import com.electronwill.nightconfig.core.Config;
import com.electronwill.nightconfig.toml.TomlFormat;
import cpw.mods.jarhandling.JarContentsBuilder;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.zip.ZipFile;
import net.neoforged.bus.api.BusBuilder;
import net.neoforged.bus.api.Event;
import net.neoforged.fml.loading.moddiscovery.readers.JarModsDotTomlModFileReader;
import net.neoforged.neoforgespi.locating.ModFileDiscoveryAttributes;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Handle;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.LdcInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.sinytra.connector.forge.loader.ForgeEventBridge;
import org.sinytra.connector.forge.transform.Forge52Symbols;

/** Exact approved original Clumps static adaptation, not a game/Mixin behavior pass. */
public final class ForgeClumpsTransformTest {
    private static int assertions;
    public static void main(String[] args) throws Exception {
        Path input = Path.of(args[0]);
        String sourceHash = Forge52JarAdapter.sha256(input);
        check(sourceHash.equals("e1de425ddd6f2b5c195c37a008d9fbc2c00c32fe1e214d76c63ab35446d13c19"), "exact approved original");
        var result = Forge52JarAdapter.adapt(input, Files.createTempDirectory("forge-clumps-static"), "SERVER");
        check(Forge52JarAdapter.sha256(input).equals(sourceHash), "original unchanged");
        try (ZipFile original = new ZipFile(input.toFile()); ZipFile output = new ZipFile(result.output().toFile())) {
            for (String resource : List.of("clumps.mixins.json", "META-INF/MANIFEST.MF", "META-INF/mods.toml",
                "META-INF/services/com.blamejared.clumps.platform.IEventHelper", "META-INF/services/com.blamejared.clumps.platform.IPlatformHelper"))
                check(java.util.Arrays.equals(original.getInputStream(original.getEntry(resource)).readAllBytes(), output.getInputStream(output.getEntry(resource)).readAllBytes()), "original resource bytes retained " + resource);
            check(output.getEntry("clumps.refmap.json") == null, "upstream missing refmap not invented");
            Config config = TomlFormat.instance().createParser().parse(new String(output.getInputStream(output.getEntry(Forge52JarAdapter.TARGET_TOML)).readAllBytes(), StandardCharsets.UTF_8));
            List<Config> configs = config.get("mixins");
            check(configs.size() == 1 && configs.getFirst().get("config").equals("clumps.mixins.json"), "one native FML Mixin registration");
            check(!config.contains("services"), "automatic module service usage is implicit; no invalid uses declarations");
            int postCalls = 0;
            var entries = output.entries();
            while (entries.hasMoreElements()) {
                var entry = entries.nextElement(); if (!entry.getName().endsWith(".class")) continue;
                byte[] bytes = output.getInputStream(entry).readAllBytes();
                check(!new String(bytes, StandardCharsets.ISO_8859_1).contains("net/minecraftforge/"), "no unmapped Forge symbol " + entry.getName());
                ClassNode node = new ClassNode(); new ClassReader(bytes).accept(node, 0);
                for (var method : node.methods) for (var instruction : method.instructions) {
                    if (instruction instanceof MethodInsnNode call && call.owner.endsWith("/ForgeEventBridge")) {
                        check(call.getOpcode() == Opcodes.INVOKESTATIC && call.desc.endsWith(";)Z"), "post boolean opcode/descriptor"); postCalls++;
                    }
                }
            }
            check(postCalls == 3, "all three real Clumps post sites rewritten");
        }
        var file = JarModsDotTomlModFileReader.createModFile(new JarContentsBuilder().paths(result.output()).build(), ModFileDiscoveryAttributes.DEFAULT);
        var descriptor = file.getSecureJar().moduleDataProvider().descriptor();
        check(descriptor.isAutomatic() && descriptor.provides().size() == 2 && descriptor.uses().isEmpty(), "actual FML automatic module descriptor preserves providers");
        check(file.getModInfos().size() == 1 && file.getModInfos().getFirst().getModId().equals("clumps"), "actual FML metadata identity");
        try (var loader = new URLClassLoader(new java.net.URL[]{result.output().toUri().toURL()}, ForgeClumpsTransformTest.class.getClassLoader())) {
            for (String name : List.of("ValueEvent", "RepairEvent")) {
                Class<?> type = Class.forName("com.blamejared.clumps.api.events." + name, true, loader);
                Event event = (Event) type.getConstructors()[0].newInstance(null, 7);
                AtomicInteger seen = new AtomicInteger();
                var bus = BusBuilder.builder().build();
                bus.addListener((Class<Event>)(Class<?>)type, received -> {
                    check(received == event, "real transformed " + name + " identity");
                    try { type.getMethod("setValue", int.class).invoke(received, 11); }
                    catch (ReflectiveOperationException e) { throw new AssertionError(e); }
                    seen.incrementAndGet();
                });
                check(!ForgeEventBridge.post(bus, event), "real noncancelable " + name + " returns false");
                check((int)type.getMethod("getValue").invoke(event) == 11 && seen.get() == 1, "real " + name + " mutable value delivered once");
            }
        }
        ClassWriter cw = new ClassWriter(0); cw.visit(65, Opcodes.ACC_PUBLIC, "PostHandle", null, "java/lang/Object", null);
        var method = cw.visitMethod(Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC, "handle", "()V", null, null); method.visitCode();
        method.visitLdcInsn(new Handle(Opcodes.H_INVOKEINTERFACE, "net/minecraftforge/eventbus/api/IEventBus", "post", "(Lnet/minecraftforge/eventbus/api/Event;)Z", true));
        method.visitInsn(Opcodes.POP); method.visitInsn(Opcodes.RETURN); method.visitMaxs(1, 0); method.visitEnd(); cw.visitEnd();
        ClassNode node = new ClassNode(); new ClassReader(Forge52Symbols.transform(cw.toByteArray(), new TreeSet<>())).accept(node, 0);
        Handle handle = (Handle)((LdcInsnNode)node.methods.getFirst().instructions.getFirst()).cst;
        check(handle.getTag() == Opcodes.H_INVOKESTATIC && handle.getOwner().endsWith("/ForgeEventBridge") && handle.getDesc().startsWith("(Lnet/neoforged/bus/api/IEventBus;"), "unbound post method handle preserves receiver argument");
        System.out.println("Forge Clumps static adapter: " + assertions + " assertions PASS; no game launch or Mixin behavior claim");
    }
    private static void check(boolean condition, String label) { assertions++; if (!condition) throw new AssertionError(label); }
}
