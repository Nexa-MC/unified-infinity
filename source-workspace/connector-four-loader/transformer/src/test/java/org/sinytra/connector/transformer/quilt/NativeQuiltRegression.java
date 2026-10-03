package org.sinytra.connector.transformer.quilt;

import net.fabricmc.api.EnvType;
import net.fabricmc.loader.impl.metadata.*;
import net.minecraftforge.fart.api.Transformer;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.jar.*;

public final class NativeQuiltRegression {
    private static final String BASE = "{\"schema_version\":1,\"quilt_loader\":{\"group\":\"dev.infinity\",\"id\":\"native-test\",\"version\":\"1.0.0+raw\",\"intermediate_mappings\":\"net.fabricmc:intermediary\"%s}%s}";
    private static int assertions;
    private static LoaderModMetadata parse(String extra, String root) throws Exception { return parseText(BASE.formatted(extra, root), false); }
    private static LoaderModMetadata parseText(String text, boolean managed) throws Exception {
        return NativeQuiltMetadata.parse(new ByteArrayInputStream(text.getBytes(StandardCharsets.UTF_8)), "/original/native.jar", new VersionOverrides(), new DependencyOverrides(Files.createTempDirectory("quilt-dep-test")), managed);
    }
    private static void check(boolean condition, String name) { assertions++; if (!condition) throw new AssertionError(name); }
    private static void reject(String extra, String root, String message) throws Exception {
        try { parse(extra, root); throw new AssertionError("accepted " + message); } catch (IOException | ParseMetadataException expected) { check(expected.getMessage().contains(message), expected.toString()); }
    }
    public static void main(String[] args) throws Exception {
        LoaderModMetadata metadata = parse(",\"entrypoints\":{\"pre_launch\":[\"A\",{\"adapter\":\"default\",\"value\":\"B::start\"}],\"init\":\"C\"},\"depends\":[{\"id\":\"minecraft\",\"versions\":{\"any\":[\"=1.21.1\",\"=1.21\"]}}]", ",\"minecraft\":{\"environment\":\"dedicated_server\"},\"mixin\":[{\"config\":\"client.json\",\"environment\":\"client\"},\"common.json\"],\"access_widener\":[\"test.aw\"],\"custom_unknown\":{\"retained\":true}");
        check(metadata.getId().equals("native-test"), "original id");
        check(metadata.getVersion().getFriendlyString().equals("1.0.0+raw"), "raw version");
        check(metadata.getEntrypoints("pre_launch").get(1).getValue().equals("B::start"), "entrypoint order and reference");
        check(metadata.getEntrypoints("init").size() == 1, "native init key");
        check(metadata.getMixinConfigs(EnvType.SERVER).equals(List.of("common.json")), "mixin side exclusion");
        check(metadata.getMixinConfigs(EnvType.CLIENT).size() == 2, "mixin side inclusion");
        check(metadata.getClassTweaker().equals("test.aw"), "single AW");
        check(metadata.loadsInEnvironment(EnvType.SERVER) && !metadata.loadsInEnvironment(EnvType.CLIENT), "native side");
        check(metadata.getCustomValue(NativeQuiltMetadata.RAW_KEY).getAsObject().get("custom_unknown").getAsObject().get("retained").getAsBoolean(), "full native AST");
        check(metadata.getCustomValue("infinity:quilt_source").getAsString().equals("/original/native.jar"), "original archive path");
        check(metadata.getDependencies().iterator().next().matches(net.fabricmc.loader.api.Version.parse("1.21.1")), "OR versions yes");
        check(!metadata.getDependencies().iterator().next().matches(net.fabricmc.loader.api.Version.parse("1.20.1")), "OR versions no");
        reject(",\"depends\":[[\"one\",\"two\"]]", "", "nested alternatives");
        reject(",\"depends\":[{\"id\":\"one\",\"unless\":\"two\"}]", "", "unless");
        reject(",\"depends\":[{\"id\":\"g:one\"}]", "", "group-qualified");
        reject(",\"depends\":[{\"id\":\"one\",\"optional\":true}]", "", "optional");
        reject(",\"depends\":[{\"id\":\"one\",\"versions\":{\"all\":[\">=1\",\"<2\"]}}]", "", "versions.any");
        reject(",\"depends\":[{\"id\":\"one\",\"versions\":\"^1.2.3\"}]", "", "unsupported semantic version");
        reject(",\"depends\":[{\"id\":\"one\",\"versions\":\"nonsense\"}]", "", "unsupported semantic version");
        reject(",\"provides\":[\"alias\"]", "", "provides");
        reject(",\"load_type\":\"if_required\"", "", "load_type");
        reject(",\"language_adapters\":{\"custom\":\"Adapter\"}", "", "language_adapters");
        reject(",\"jars\":[\"nested.jar\"]", "", "jars");
        reject("", ",\"access_widener\":[\"one.aw\",\"two.aw\"]", "one access_widener");
        reject("", ",\"mixin\":\"../escape.json\"", "unsafe resource");
        reject(",\"plugins\":[\"Plugin\"]", "", "plugins");
        try { parseText(BASE.formatted(",\"id\":\"duplicate\"", ""), false); throw new AssertionError("duplicate accepted"); } catch (IOException expected) { check(expected.getMessage().contains("duplicate key"), "duplicate reject"); }
        try { parseText(BASE.formatted("", "") + "{}", false); throw new AssertionError("trailing accepted"); } catch (IOException expected) { check(true, "trailing reject"); }
        try { parseText(BASE.formatted("", "").replace("\"schema_version\"", "/*comment*/\"schema_version\""), false); throw new AssertionError("comment accepted"); } catch (IOException expected) { check(true, "comment reject"); }
        for (String input : args) try (JarFile jar = new JarFile(input)) {
            check(QuiltJarAdapter.isManagedQsl(Path.of(input)), "managed QSL digest");
            String json = new String(jar.getInputStream(jar.getJarEntry("quilt.mod.json")).readAllBytes(), StandardCharsets.UTF_8);
            LoaderModMetadata qsl = parseText(json, true);
            check(qsl.getLicense().contains("Apache-2.0"), "QSL attribution");
            check(qsl.getVersion().getFriendlyString().equals("10.0.0-alpha.5+1.21.1"), "QSL version");
            for (EnvType side : EnvType.values()) {
                QuiltJarAdapter adapter = new QuiltJarAdapter(Path.of(input), side);
                int processed = 0;
                for (var it = jar.entries(); it.hasMoreElements();) {
                    var entry = it.nextElement();
                    if (entry.getName().endsWith(".class")) {
                        adapter.process(Transformer.ClassEntry.create(entry.getName(), entry.getTime(), jar.getInputStream(entry).readAllBytes()));
                        processed++;
                    }
                }
                check(processed > 0, "QSL side preprocessing " + side);
            }
        }
        assertions += NativeQuiltPrereleaseRegression.run();
        testSingleHostResolver();
        testSideStripper();
        System.out.println("NATIVE_QUILT_REGRESSION assertions=" + assertions + " PASS");
    }
    private static void testSingleHostResolver() throws Exception {
        var minecraft = new net.fabricmc.loader.impl.discovery.BuiltinMetadataWrapper(new BuiltinModMetadata.Builder("minecraft", "1.21.1").build());
        var java = new net.fabricmc.loader.impl.discovery.BuiltinMetadataWrapper(new BuiltinModMetadata.Builder("java", "21").build());
        var loader = new net.fabricmc.loader.impl.discovery.BuiltinMetadataWrapper(new BuiltinModMetadata.Builder("quilt_loader", "0.30.1").build());
        for (String constraint : List.of(">=0.25.0", ">=0.16.0-", ">=0.31.0", ">=0.31.0-")) {
            var nativeMod = parse(",\"depends\":[{\"id\":\"minecraft\",\"versions\":\"=1.21.1\"},{\"id\":\"java\",\"versions\":\">=21\"},{\"id\":\"quilt_loader\",\"versions\":\"" + constraint + "\"}]", "");
            var candidates = new ArrayList<net.fabricmc.loader.impl.discovery.ModCandidateImpl>();
            for (var metadata : List.of(minecraft, java, loader, nativeMod)) candidates.add(net.fabricmc.loader.impl.discovery.ModCandidateImpl.createPlain(List.of(Path.of("/test/" + metadata.getId() + ".jar")), metadata, false, List.of()));
            try {
                var result = net.fabricmc.loader.impl.discovery.ModResolver.resolve(candidates, EnvType.SERVER, Map.of());
                check(!constraint.startsWith(">=0.31.0") && result.size() == 4, "single host resolver selection");
            } catch (net.fabricmc.loader.impl.discovery.ModResolutionException e) {
                check(constraint.startsWith(">=0.31.0"), "loader version rejected by same solver");
            }
        }
        var missing = parse(",\"depends\":[\"native_missing_dependency\"]", "");
        try {
            net.fabricmc.loader.impl.discovery.ModResolver.resolve(List.of(net.fabricmc.loader.impl.discovery.ModCandidateImpl.createPlain(List.of(Path.of("/test/missing.jar")), missing, false, List.of())), EnvType.SERVER, Map.of());
            throw new AssertionError("Missing native Quilt dependency was accepted");
        } catch (net.fabricmc.loader.impl.discovery.ModResolutionException e) { check(true, "missing dependency rejected before entrypoint definition"); }
    }
    private static void testSideStripper() throws Exception {
        Path file = Files.createTempFile("quilt-empty", ".jar"); try (JarOutputStream jar = new JarOutputStream(Files.newOutputStream(file))) {}
        QuiltJarAdapter adapter = new QuiltJarAdapter(file, EnvType.SERVER);
        ClassNode cls = new ClassNode(); cls.version = Opcodes.V21; cls.access = Opcodes.ACC_PUBLIC; cls.name = "fixture/Test"; cls.superName = "java/lang/Object";
        MethodNode method = new MethodNode(Opcodes.ACC_PUBLIC, "client", "()V", null, null); method.invisibleAnnotations = List.of(new AnnotationNode("Lorg/quiltmc/loader/api/minecraft/ClientOnly;")); method.instructions.add(new InsnNode(Opcodes.RETURN)); cls.methods.add(method);
        MethodNode retained = new MethodNode(Opcodes.ACC_PUBLIC, "common", "()V", null, null); retained.instructions.add(new InsnNode(Opcodes.RETURN)); cls.methods.add(retained);
        ClassWriter writer = new ClassWriter(0); cls.accept(writer);
        Transformer.ClassEntry output = adapter.process(Transformer.ClassEntry.create("fixture/Test.class", 0, writer.toByteArray()));
        ClassNode result = new ClassNode(); new ClassReader(output.getData()).accept(result, 0);
        check(result.methods.size() == 1 && result.methods.get(0).name.equals("common"), "wrong-side member stripped");
        cls.invisibleAnnotations = List.of(new AnnotationNode("Lorg/quiltmc/loader/api/minecraft/ClientOnly;")); writer = new ClassWriter(0); cls.accept(writer);
        check(adapter.process(Transformer.ClassEntry.create("fixture/Test.class", 0, writer.toByteArray())) == null, "wrong-side class stripped");
        Files.delete(file);
    }
}
