package org.sinytra.connector.transformer.quilt;

import com.google.gson.*;
import net.fabricmc.api.EnvType;
import net.minecraftforge.fart.api.Transformer;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.*;
import java.util.*;
import java.util.jar.JarFile;

/** One host transformation pass. Original QSL modules remain untouched on disk. */
public final class QuiltJarAdapter implements Transformer {
    private static final Set<String> MANAGED_SHA256 = Set.of(
        "7eb4ec613f901ef7232f9f84ee91be5576f00682f32ad9c9f7b1a679bcf82465",
        "1a1f9b72c38e2475b471df1dcff7992d6ae4955e8a2cd8288bb3ba3986768aa4");
    private static final String CLIENT = "Lorg/quiltmc/loader/api/minecraft/ClientOnly;";
    private static final String SERVER = "Lorg/quiltmc/loader/api/minecraft/DedicatedServerOnly;";
    private final EnvType environment;
    private final boolean managedQsl;
    private final Set<String> removedPackages = new HashSet<>();

    public QuiltJarAdapter(Path input, EnvType environment) throws IOException {
        this.environment = environment;
        this.managedQsl = isManagedQsl(input);
        try (JarFile jar = new JarFile(input.toFile())) {
            for (var it = jar.entries(); it.hasMoreElements();) {
                var entry = it.nextElement();
                if (entry.getName().endsWith("/package-info.class")) {
                    ClassNode node = new ClassNode();
                    try (InputStream in = jar.getInputStream(entry)) { new ClassReader(in).accept(node, ClassReader.SKIP_CODE | ClassReader.SKIP_DEBUG | ClassReader.SKIP_FRAMES); }
                    if (wrongSide(node.invisibleAnnotations) != null) removedPackages.add(node.name.substring(0, node.name.lastIndexOf('/')));
                }
            }
        }
    }

    public static boolean isManagedQsl(Path input) throws IOException {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (InputStream in = Files.newInputStream(input)) { byte[] b = new byte[65536]; int n; while ((n = in.read(b)) != -1) digest.update(b, 0, n); }
            return MANAGED_SHA256.contains(HexFormat.of().formatHex(digest.digest()));
        } catch (NoSuchAlgorithmException e) { throw new AssertionError(e); }
    }

    @Override public ResourceEntry process(ResourceEntry entry) {
        if (managedQsl && entry.getName().equals("quilt_base.mixins.json")) {
            JsonObject json = JsonParser.parseString(new String(entry.getData(), StandardCharsets.UTF_8)).getAsJsonObject();
            // One explicit bootstrap owner: ConnectorLoader invokes native init and side-init once.
            // Preserve QSL classes/API/metadata/license; suppress its competing bootstrap/test mixins.
            for (String side : List.of("mixins", "client", "server")) json.add(side, new JsonArray());
            return ResourceEntry.create(entry.getName(), entry.getTime(), json.toString().getBytes(StandardCharsets.UTF_8));
        }
        return entry;
    }

    @Override public ClassEntry process(ClassEntry entry) {
        ClassNode node = new ClassNode(); new ClassReader(entry.getData()).accept(node, 0);
        if (managedQsl && node.name.startsWith("org/quiltmc/qsl/base/mixin/")) return null;
        for (FieldNode f : node.fields) if (wrongSide(f.invisibleTypeAnnotations) != null)
            throw new IllegalArgumentException("Unsupported Quilt field type-use side annotation in " + node.name + "." + f.name);
        for (MethodNode m : node.methods) if (wrongSide(m.invisibleTypeAnnotations) != null)
            throw new IllegalArgumentException("Unsupported Quilt method type-use side annotation in " + node.name + "." + m.name);
        String pkg = node.name.contains("/") ? node.name.substring(0, node.name.lastIndexOf('/')) : "";
        if (removedPackages.contains(pkg) || wrongSide(node.invisibleAnnotations) != null) return null;
        Set<MethodNode> removed = new HashSet<>();
        for (MethodNode method : node.methods) {
            AnnotationNode annotation = wrongSide(method.invisibleAnnotations);
            if (annotation != null) {
                removed.add(method);
                if (stripLambdas(annotation)) collectLambdas(node, method, removed);
            }
        }
        boolean changed = node.methods.removeAll(removed);
        changed |= node.fields.removeIf(field -> wrongSide(field.invisibleAnnotations) != null);
        if (node.invisibleTypeAnnotations != null) {
            SortedSet<Integer> indices = new TreeSet<>(Comparator.reverseOrder());
            for (TypeAnnotationNode a : node.invisibleTypeAnnotations) {
                if (!isWrong(a)) continue;
                TypeReference ref = new TypeReference(a.typeRef);
                if (ref.getSort() != TypeReference.CLASS_EXTENDS || ref.getSuperTypeIndex() == -1 || a.typePath != null)
                    throw new IllegalArgumentException("Unsupported Quilt side type annotation in " + node.name);
                indices.add(ref.getSuperTypeIndex());
            }
            for (int index : indices) { node.interfaces.remove(index); changed = true; }
            if (!indices.isEmpty()) {
                node.invisibleTypeAnnotations.removeIf(a -> new TypeReference(a.typeRef).getSort() == TypeReference.CLASS_EXTENDS && indices.contains(new TypeReference(a.typeRef).getSuperTypeIndex()));
                for (TypeAnnotationNode a : node.invisibleTypeAnnotations) {
                    TypeReference ref = new TypeReference(a.typeRef);
                    if (ref.getSort() == TypeReference.CLASS_EXTENDS && ref.getSuperTypeIndex() >= 0) {
                        int old = ref.getSuperTypeIndex(); int shift = (int) indices.stream().filter(i -> i < old).count();
                        a.typeRef = TypeReference.newSuperTypeReference(old - shift).getValue();
                    }
                }
                // Generic interface signatures need exact structural editing; fail closed instead of stale signature metadata.
                if (node.signature != null) throw new IllegalArgumentException("Quilt side-stripped generic interface signature unsupported in " + node.name);
            }
        }
        if (!changed) return entry;
        ClassWriter writer = new ClassWriter(0); node.accept(writer);
        return ClassEntry.create(entry.getName(), entry.getTime(), writer.toByteArray());
    }
    private AnnotationNode wrongSide(List<? extends AnnotationNode> annotations) {
        if (annotations != null) for (AnnotationNode a : annotations) if (isWrong(a)) return a;
        return null;
    }
    private boolean isWrong(AnnotationNode a) { return environment == EnvType.SERVER ? CLIENT.equals(a.desc) : SERVER.equals(a.desc); }
    private static boolean stripLambdas(AnnotationNode annotation) {
        if (annotation.values != null) for (int i = 0; i < annotation.values.size(); i += 2)
            if (annotation.values.get(i).equals("stripLambdas")) return Boolean.TRUE.equals(annotation.values.get(i + 1));
        return true;
    }
    private static void collectLambdas(ClassNode node, MethodNode method, Set<MethodNode> result) {
        for (AbstractInsnNode instruction : method.instructions) if (instruction instanceof InvokeDynamicInsnNode indy) {
            for (Object arg : indy.bsmArgs) if (arg instanceof Handle h && h.getOwner().equals(node.name) && h.getName().startsWith("lambda$")) {
                for (MethodNode candidate : node.methods) if (candidate.name.equals(h.getName()) && candidate.desc.equals(h.getDesc()) && result.add(candidate)) collectLambdas(node, candidate, result);
            }
        }
    }
}
