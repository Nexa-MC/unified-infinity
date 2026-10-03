package org.sinytra.connector.forge.discovery;

import com.electronwill.nightconfig.core.Config;
import com.electronwill.nightconfig.toml.TomlFormat;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeSet;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipOutputStream;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Handle;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.Type;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.sinytra.connector.forge.transform.Forge52Symbols;

public final class ForgeAdapterTest {
    private static int assertions;
    private static final String TOML = """
        modLoader="javafml"
        loaderVersion="[52,53)"
        license="MIT"
        [[mods]]
        modId="test_mod"
        version="1.0"
        [[dependencies.test_mod]]
        modId="forge"
        mandatory=true
        versionRange="[52.1.0,52.2)"
        ordering="AFTER"
        side="BOTH"
        [[dependencies.test_mod]]
        modId="optional_mod"
        mandatory=false
        versionRange="[1,2)"
        ordering="BEFORE"
        side="CLIENT"
        """;

    public static void main(String[] args) throws Exception {
        metadata(); symbols(); jar(Path.of(args[0]));
        System.out.println("Forge static adapter tests: " + assertions + " assertions PASS");
    }

    private static void metadata() {
        var projected = Forge52Metadata.project(TOML, "DEDICATED_SERVER");
        Config config = TomlFormat.instance().createParser().parse(projected.toml());
        check(config.get("modLoader").equals("unified_forge_52"), "distinct provider");
        check(config.get("loaderVersion").equals("[1.0.0]"), "provider version independently projected");
        List<Config> deps = config.get("dependencies.test_mod");
        check(deps.get(0).get("modId").equals("unified_forge52_adapter"), "explicit capability");
        check(deps.get(0).get("versionRange").equals("[52.1.0,52.2)"), "Forge range retained");
        check(deps.get(0).get("type").equals("required"), "mandatory true required");
        check(deps.get(1).get("type").equals("optional"), "mandatory false optional");
        check(deps.get(1).get("side").equals("CLIENT") && deps.get(1).get("ordering").equals("BEFORE"), "side/order retained");
        check(projected.audit().get("sourceLoaderRange").equals("[52,53)"), "source language retained");
        rejects(() -> Forge52Metadata.project(TOML.replace("[52,53)", "[53,)"), "SERVER"), "wrong loader range");
        rejects(() -> Forge52Metadata.project(TOML.replace("[52.1.0,52.2)", "[52.2,)"), "SERVER"), "wrong capability range");
        rejects(() -> Forge52Metadata.project(TOML.replace("modId=\"forge\"", "modId=\"minecraft\"").replace("[52.1.0,52.2)", "[1.20.1]"), "SERVER"), "wrong MC range");
        rejects(() -> Forge52Metadata.project(TOML.replace("mandatory=false", "type=\"optional\""), "SERVER"), "missing mandatory fails");
        rejects(() -> Forge52Metadata.project(TOML + "\n[[mods]]\nmodId=\"test_mod\"\nversion=\"2\"", "SERVER"), "duplicate ID fails");
        rejects(() -> Forge52Metadata.project(TOML + "\n[features.test_mod]\njavaVersion=\"[22,)\"", "SERVER"), "wrong Java range fails");
        rejects(() -> Forge52Metadata.project(TOML + "\n[[mixins]]\nconfig=\"unsupported.mixins.json\"", "SERVER"), "unsupported mixin metadata");
        String notThisSide = TOML.replace("[52.1.0,52.2)", "[99,)").replace("side=\"BOTH\"", "side=\"CLIENT\"");
        check(Forge52Metadata.project(notThisSide, "SERVER") != null, "inactive side kept for host filtering");
        rejects(() -> Forge52Metadata.project(notThisSide, "CLIENT"), "applicable side enforces version");
    }

    private static void symbols() {
        var audit = new TreeSet<String>();
        byte[] original = methodFixture("net/minecraftforge/event/TickEvent$ServerTickEvent$Post", "haveTime", "()Z", Opcodes.INVOKEVIRTUAL, false);
        byte[] adapted = Forge52Symbols.transform(original, audit);
        ClassNode node = new ClassNode(); new ClassReader(adapted).accept(node, 0);
        MethodInsnNode call = (MethodInsnNode)node.methods.get(0).instructions.get(1);
        check(call.owner.equals("net/neoforged/neoforge/event/tick/ServerTickEvent$Post") && call.name.equals("hasTime"), "exact tick member adaptation");
        check(audit.stream().anyMatch(s -> s.contains("haveTime()Z")), "member audit");
        byte[] post = Forge52Symbols.transform(methodFixture("net/minecraftforge/eventbus/api/IEventBus", "post", "(Lnet/minecraftforge/eventbus/api/Event;)Z", Opcodes.INVOKEINTERFACE, true), new TreeSet<>());
        ClassNode postNode = new ClassNode(); new ClassReader(post).accept(postNode, 0);
        MethodInsnNode postCall = (MethodInsnNode) postNode.methods.get(0).instructions.get(1);
        check(postCall.getOpcode() == Opcodes.INVOKESTATIC && postCall.owner.endsWith("/ForgeEventBridge")
            && postCall.desc.equals("(Lnet/neoforged/bus/api/IEventBus;Lnet/neoforged/bus/api/Event;)Z"), "boolean post uses semantic bridge");
        rejects(() -> Forge52Symbols.transform(methodFixture("net/minecraftforge/registries/RegistryObject", "orElse", "(Ljava/lang/Object;)Ljava/lang/Object;", Opcodes.INVOKEVIRTUAL, false), new TreeSet<>()), "unknown facade method fails");
        rejects(() -> Forge52Symbols.transform(methodFixture("net/minecraft/server/MinecraftServer", "m_123_", "()V", Opcodes.INVOKEVIRTUAL, false), new TreeSet<>()), "SRG namespace rejected");
        ClassWriter cw = new ClassWriter(0); cw.visit(65, Opcodes.ACC_PUBLIC, "Fixture", null, "java/lang/Object", null);
        var method = cw.visitMethod(Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC, "lambda", "()V", null, null);
        method.visitCode();
        method.visitLdcInsn(new Handle(Opcodes.H_INVOKEVIRTUAL, "net/minecraftforge/event/TickEvent$ServerTickEvent$Post", "haveTime", "()Z", false));
        method.visitInsn(Opcodes.POP);
        method.visitLdcInsn(Type.getMethodType("(Lnet/minecraftforge/fml/event/lifecycle/FMLCommonSetupEvent;)V"));
        method.visitInsn(Opcodes.POP); method.visitInsn(Opcodes.RETURN); method.visitMaxs(1, 0); method.visitEnd(); cw.visitEnd();
        audit.clear(); Forge52Symbols.transform(cw.toByteArray(), audit);
        check(audit.stream().anyMatch(s -> s.contains("hasTime")), "method handle adapted");
        check(audit.stream().anyMatch(s -> s.contains("FMLCommonSetupEvent")), "method type adapted");
        cw = new ClassWriter(0); cw.visit(65, Opcodes.ACC_PUBLIC, "Fixture", null, "net/minecraftforge/eventbus/api/Event", null); cw.visitEnd();
        byte[] subclass = cw.toByteArray();
        check(new ClassReader(Forge52Symbols.transform(subclass, new TreeSet<>())).getSuperName().equals("net/neoforged/bus/api/Event"), "plain custom Event gets native superclass");
        cw = new ClassWriter(0); cw.visit(65, Opcodes.ACC_PUBLIC, "Fixture", null, "net/minecraftforge/eventbus/api/Event", null);
        cw.visitAnnotation("Lnet/minecraftforge/eventbus/api/Cancelable;", true).visitEnd(); cw.visitEnd();
        byte[] cancelledClass = cw.toByteArray(); rejects(() -> Forge52Symbols.transform(cancelledClass, new TreeSet<>()), "custom Cancelable annotation still rejected");
        rejects(() -> Forge52Symbols.transform(methodFixture("ExampleEvent", "setCanceled", "(Z)V", Opcodes.INVOKEVIRTUAL, false), new TreeSet<>(), java.util.Set.of("ExampleEvent")), "inherited unsupported event methods rejected");
        cw = new ClassWriter(0); cw.visit(65, Opcodes.ACC_PUBLIC, "Fixture", null, "java/lang/Object", null);
        cw.visitField(Opcodes.ACC_STATIC, "phase", "Lnet/minecraftforge/event/TickEvent$Phase;", null, null).visitEnd(); cw.visitEnd();
        byte[] unsupported = cw.toByteArray(); rejects(() -> Forge52Symbols.transform(unsupported, new TreeSet<>()), "base tick phase rejected");
    }

    private static void jar(Path probe) throws Exception {
        Path temp = Files.createTempDirectory("forge-static-tests-");
        String originalHash = Forge52JarAdapter.sha256(probe);
        var first = Forge52JarAdapter.adapt(probe, temp.resolve("cache"), "SERVER");
        check(!first.cacheHit(), "first adaptation miss");
        check(Forge52JarAdapter.sha256(probe).equals(originalHash), "original bytes unchanged");
        check(originalHash.equals("3a016e8b8340c7c10b6490f15bb7452c1555363035c7373f4d81ccfacfde15fe"), "genuine independently compiled Forge probe");
        var second = Forge52JarAdapter.adapt(probe, temp.resolve("cache"), "SERVER");
        check(second.cacheHit() && first.outputSha256().equals(second.outputSha256()), "verified warm cache");
        try (ZipFile source = new ZipFile(probe.toFile()); ZipFile derived = new ZipFile(first.output().toFile())) {
            check(Arrays.equals(source.getInputStream(source.getEntry(Forge52JarAdapter.SOURCE_TOML)).readAllBytes(), derived.getInputStream(derived.getEntry(Forge52JarAdapter.SOURCE_TOML)).readAllBytes()), "original metadata retained verbatim");
            check(derived.getEntry(Forge52JarAdapter.TARGET_TOML) != null, "host metadata projected");
            String audit = new String(derived.getInputStream(derived.getEntry(Forge52JarAdapter.AUDIT_RESOURCE)).readAllBytes(), StandardCharsets.UTF_8);
            check(audit.contains(originalHash) && audit.contains("hasTime") && audit.contains("unified_forge52_adapter"), "source/rules/capability audit embedded");
            var entries = derived.entries();
            while (entries.hasMoreElements()) {
                var e = entries.nextElement(); if (!e.getName().endsWith(".class")) continue;
                ClassReader reader = new ClassReader(derived.getInputStream(e));
                check(!new String(reader.b, StandardCharsets.ISO_8859_1).contains("net/minecraftforge/"), "no runtime Forge implementation symbols " + e.getName());
            }
        }
        Files.writeString(first.output(), "corrupt");
        var repaired = Forge52JarAdapter.adapt(probe, temp.resolve("cache"), "SERVER");
        check(!repaired.cacheHit() && repaired.outputSha256().equals(first.outputSha256()), "corrupt cache regenerated deterministically");
        var client = Forge52JarAdapter.adapt(probe, temp.resolve("cache"), "CLIENT");
        check(!client.output().equals(first.output()), "side-sensitive cache key");
        var fixture = new LinkedHashMap<String, byte[]>(); fixture.put(Forge52JarAdapter.SOURCE_TOML, TOML.getBytes(StandardCharsets.UTF_8));
        fixture.put("../bad", new byte[0]); negativeJar(temp, fixture, "unsafe path"); fixture.remove("../bad");
        fixture.put("META-INF/coremods.json", "{}".getBytes(StandardCharsets.UTF_8)); negativeJar(temp, fixture, "coremods resource rejected"); fixture.remove("META-INF/coremods.json");
        fixture.put("fabric.mod.json", "{}".getBytes(StandardCharsets.UTF_8)); negativeJar(temp, fixture, "ambiguous descriptors rejected"); fixture.remove("fabric.mod.json");
        fixture.put("META-INF/services/Test", new byte[0]); negativeJar(temp, fixture, "services rejected"); fixture.remove("META-INF/services/Test");
        fixture.put("META-INF/a.SF", new byte[0]); negativeJar(temp, fixture, "signed JAR rejected"); fixture.remove("META-INF/a.SF");
        fixture.put("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\nMixinConfigs: unsupported.json\n\n".getBytes(StandardCharsets.UTF_8)); negativeJar(temp, fixture, "manifest mixins rejected"); fixture.remove("META-INF/MANIFEST.MF");
        fixture.put(Forge52JarAdapter.SOURCE_TOML, new byte[1024 * 1024 + 1]); negativeJar(temp, fixture, "metadata bound");
    }

    private static void negativeJar(Path temp, Map<String, byte[]> entries, String label) throws Exception {
        Path jar = Files.createTempFile(temp, "negative", ".jar");
        try (ZipOutputStream stream = new ZipOutputStream(Files.newOutputStream(jar))) {
            for (var e : entries.entrySet()) { stream.putNextEntry(new ZipEntry(e.getKey())); stream.write(e.getValue()); stream.closeEntry(); }
        }
        Path cache = Files.createTempDirectory(temp, "failure-cache");
        rejects(() -> Forge52JarAdapter.adapt(jar, cache, "SERVER"), label);
        try (var files = Files.list(cache)) { check(files.findAny().isEmpty(), "failure never cached: " + label); }
    }

    private static byte[] methodFixture(String owner, String name, String desc, int opcode, boolean iface) {
        ClassWriter cw = new ClassWriter(0); cw.visit(65, Opcodes.ACC_PUBLIC, "Fixture", null, "java/lang/Object", null);
        var mv = cw.visitMethod(Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC, "test", "()V", null, null);
        mv.visitCode(); mv.visitInsn(Opcodes.ACONST_NULL); mv.visitMethodInsn(opcode, owner, name, desc, iface); mv.visitInsn(Opcodes.RETURN); mv.visitMaxs(3, 0); mv.visitEnd(); cw.visitEnd();
        return cw.toByteArray();
    }
    private interface Checked { void run() throws Exception; }
    private static void rejects(Checked action, String message) {
        try { action.run(); throw new AssertionError("Expected rejection: " + message); }
        catch (IllegalArgumentException | java.io.IOException expected) { assertions++; }
        catch (Exception error) { throw new AssertionError("Wrong rejection: " + message, error); }
    }
    private static void check(boolean value, String message) { assertions++; if (!value) throw new AssertionError(message); }
}
