package org.sinytra.adapter.transform.param;

import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.Type;
import org.objectweb.asm.tree.*;
import org.objectweb.asm.util.CheckClassAdapter;
import org.sinytra.adapter.env.ann.ClassTarget;
import org.sinytra.adapter.env.ctx.MixinContext;
import org.sinytra.adapter.env.ctx.PatchContext;
import org.sinytra.adapter.env.ctx.PatchResult;

import java.io.InputStream;
import java.nio.file.Path;
import java.util.*;
import java.util.jar.JarFile;

/** Standalone, dependency-light regression suite for the experimental transformer. */
public final class RemoveParameterTransformerRegression {
    private static final String LOCAL = "Lcom/llamalad7/mixinextras/sugar/Local;";
    private static final String LITHIUM_ENTRY = "net/caffeinemc/mods/lithium/fabric/mixin/entity/collisions/fluid/EntityMixin.class";
    private static int tests;
    private static int failures;
    private static int checks;

    public static void main(String[] args) throws Exception {
        System.out.println("Transformer loaded from: " + RemoveParameterTransformer.class.getProtectionDomain().getCodeSource().getLocation());
        System.out.println("ASM loaded from: " + ClassReader.class.getProtectionDomain().getCodeSource().getLocation());
        Path lithium = Path.of(args[0]);
        if (args.length > 1 && args[1].equals("--lithium-only")) {
            run("real Lithium metadata via actual apply", () -> lithium(lithium));
        } else {
            run("real Lithium metadata via actual apply", () -> lithium(lithium));
            for (int visibility = 1; visibility <= 3; visibility++) {
                for (int target = 0; target < 3; target++) {
                    final int v = visibility, t = target;
                    run("apply explicit counts visibility=" + v + " target=" + t, () -> removal(v, t, true));
                }
            }
            run("apply implicit zero counts preserve inferred layout", () -> removal(3, 1, false));
            run("apply nonzero offset removes target rather than index", RemoveParameterTransformerRegression::offset);
            run("apply all parameters removed through zero", RemoveParameterTransformerRegression::removeToZero);
            run("apply no annotations keeps null arrays and zero counts", RemoveParameterTransformerRegression::noAnnotations);
            run("helper removes both channels without touching MethodParameters", RemoveParameterTransformerRegression::helperOnly);
            run("validate and empty transform are byte-identical", RemoveParameterTransformerRegression::unchanged);
            run("validate original Lithium entire class is byte-identical", () -> unchangedLithium(lithium));
            run("validate implicit metadata is byte-identical", RemoveParameterTransformerRegression::unchangedImplicit);
            run("apply static category-2 LVT at nonzero offset", () -> localVariables(true));
            run("apply instance category-2 LVT at nonzero offset", () -> localVariables(false));
            for (boolean visible : new boolean[] {true, false}) {
                for (String kind : List.of("reduced-count", "oversized-count", "negative-count", "short-array", "long-array")) {
                    run("reject " + kind + " " + (visible ? "visible" : "invisible") + " before mutation", () -> rejectLayout(visible, kind));
                }
            }
            run("second removal against stale descriptor uses live parameter count", RemoveParameterTransformerRegression::staleDescriptor);
        }
        System.out.printf("RESULT: %d tests, %d checks, %d failures%n", tests, checks, failures);
        if (failures != 0) throw new AssertionError(failures + " regression test(s) failed");
    }

    private static void lithium(Path jarPath) throws Exception {
        MethodNode original = originalLithium(jarPath).methods.stream()
            .filter(m -> m.name.equals("tryShortcutFluidPushing")).findFirst().orElseThrow();
        Type[] args = Type.getArgumentTypes(original.desc);
        equal(9, args.length, "Lithium original descriptor arguments");
        equal("Lnet/minecraft/class_6862;", args[0].getDescriptor(), "Lithium original TagKey argument");
        equal(Type.DOUBLE_TYPE, args[1], "Lithium original double argument");
        equal("Lorg/spongepowered/asm/mixin/injection/callback/CallbackInfoReturnable;", args[2].getDescriptor(), "Lithium callback argument");
        for (int i = 3; i < 9; i++) equal(Type.INT_TYPE, args[i], "Lithium integer argument " + i);
        equal(9, original.invisibleParameterAnnotations.length, "Lithium original invisible array");
        equal(9, original.invisibleAnnotableParameterCount, "Lithium original invisible count");
        check(original.visibleParameterAnnotations == null, "Lithium original has no visible parameter annotations");
        assertLocals(original, 3, "Lithium original");

        // Keep actual annotation payloads and parameter metadata; discard executable code.
        // This isolates metadata correctness without claiming that removed, live arguments
        // can be deleted from the original handler body without other adapter transforms.
        MethodNode m = new MethodNode(Opcodes.ACC_PUBLIC | Opcodes.ACC_ABSTRACT, original.name, original.desc, null, null);
        m.parameters = new ArrayList<>();
        for (ParameterNode p : original.parameters) m.parameters.add(new ParameterNode(p.name, p.access));
        m.invisibleParameterAnnotations = cloneAnnotations(original.invisibleParameterAnnotations);
        m.invisibleAnnotableParameterCount = original.invisibleAnnotableParameterCount;
        m.localVariables = new ArrayList<>();
        ClassNode owner = owner(m);
        MixinContext context = context(owner, m);
        List<Type> parameters = parameters(m);
        String originalDesc = m.desc;
        apply(owner, m, context, parameters, 0, 0);
        equal(originalDesc, m.desc, "first apply defers descriptor rewriting to caller");
        apply(owner, m, context, parameters, 0, 0);
        equal(originalDesc, m.desc, "second apply works with still-original descriptor");
        rewriteDescriptor(m, parameters);
        equal(7, Type.getArgumentTypes(m.desc).length, "Lithium after removal descriptor");
        equal(7, m.parameters.size(), "Lithium after removal MethodParameters");
        equal("cir", m.parameters.getFirst().name, "Lithium retained callback parameter");
        equal(7, m.invisibleParameterAnnotations.length, "Lithium after removal invisible array");
        // Attempt serialization before the count assertion so the immutable-base
        // negative control reproduces the actual ASM failure, not just a mismatch.
        RuntimeException serializationFailure = null;
        try { bytes(owner); }
        catch (RuntimeException e) {
            serializationFailure = e;
            System.err.println("Lithium ASM serialization failed: " + e);
            e.printStackTrace(System.err);
        }
        equal(7, m.invisibleAnnotableParameterCount, "Lithium after removal invisible count");
        if (serializationFailure != null) throw serializationFailure;
        assertLocals(m, 1, "Lithium after removal");
        MethodNode reread = roundTrip(owner);
        equal(7, reread.invisibleParameterAnnotations.length, "Lithium roundtrip invisible array");
        equal(7, reread.invisibleAnnotableParameterCount, "Lithium roundtrip invisible count");
        equal(7, Type.getArgumentTypes(reread.desc).length, "Lithium roundtrip descriptor");
        assertLocals(reread, 1, "Lithium roundtrip");
        System.out.println("  Lithium proof: original descriptor/array/count=9/9/9; transformed and roundtrip=7/7/7; @Local ordinal 0..5 at indices 1..6");
    }

    private static ClassNode originalLithium(Path path) throws Exception {
        try (JarFile jar = new JarFile(path.toFile()); InputStream in = jar.getInputStream(Objects.requireNonNull(jar.getJarEntry(LITHIUM_ENTRY)))) {
            ClassNode node = new ClassNode();
            new ClassReader(in).accept(node, 0);
            return node;
        }
    }

    private static void assertLocals(MethodNode m, int first, String label) {
        List<AnnotationNode>[] annotations = m.invisibleParameterAnnotations;
        for (int i = 0; i < first; i++) check(annotations[i] == null || annotations[i].isEmpty(), label + " unannotated prefix " + i);
        for (int ordinal = 0; ordinal < 6; ordinal++) {
            List<AnnotationNode> slot = annotations[first + ordinal];
            equal(1, slot.size(), label + " annotation count " + ordinal);
            equal(LOCAL, slot.getFirst().desc, label + " @Local descriptor " + ordinal);
            equal(List.of("ordinal", ordinal), slot.getFirst().values, label + " @Local payload " + ordinal);
        }
    }

    private static void removal(int visibility, int target, boolean explicit) {
        MethodNode m = fixture(3, visibility, explicit);
        ClassNode owner = owner(m);
        List<Type> parameters = parameters(m);
        List<AnnotationNode>[] visibleBefore = m.visibleParameterAnnotations;
        List<AnnotationNode>[] invisibleBefore = m.invisibleParameterAnnotations;
        apply(owner, m, context(owner, m), parameters, target, 0);
        rewriteDescriptor(m, parameters);
        equal(2, m.parameters.size(), "remaining named parameters");
        checkRetained(m.visibleParameterAnnotations, visibleBefore, target, "visible");
        checkRetained(m.invisibleParameterAnnotations, invisibleBefore, target, "invisible");
        equal((visibility & 1) != 0 && explicit ? 2 : 0, m.visibleAnnotableParameterCount, "visible in-memory count");
        equal((visibility & 2) != 0 && explicit ? 2 : 0, m.invisibleAnnotableParameterCount, "invisible in-memory count");
        MethodNode reread = roundTrip(owner);
        for (int i = 0, old = 0; i < 2; i++, old++) {
            if (old == target) old++;
            equal("p" + old, m.parameters.get(i).name, "retained name");
            if ((visibility & 1) != 0) equal(old, value(reread.visibleParameterAnnotations[i].getFirst(), "id"), "visible roundtrip order");
            if ((visibility & 2) != 0) equal(old, value(reread.invisibleParameterAnnotations[i].getFirst(), "id"), "invisible roundtrip order");
        }
        equal((visibility & 1) != 0 ? 2 : 0, reread.visibleAnnotableParameterCount, "visible serialized effective count");
        equal((visibility & 2) != 0 ? 2 : 0, reread.invisibleAnnotableParameterCount, "invisible serialized effective count");
    }

    private static void offset() {
        MethodNode m = fixture(4, 3, true);
        ClassNode owner = owner(m);
        List<Type> parameters = parameters(m);
        apply(owner, m, context(owner, m), parameters, 0, 2);
        rewriteDescriptor(m, parameters);
        MethodNode reread = roundTrip(owner);
        for (int i = 0; i < 3; i++) {
            int old = i < 2 ? i : i + 1;
            equal("p" + old, reread.parameters.get(i).name, "offset parameter name");
            equal(old, value(reread.visibleParameterAnnotations[i].getFirst(), "id"), "offset visible identity");
            equal(old, value(reread.invisibleParameterAnnotations[i].getFirst(), "id"), "offset invisible identity");
        }
    }

    private static void removeToZero() {
        MethodNode m = fixture(3, 3, true);
        ClassNode owner = owner(m);
        List<Type> parameters = parameters(m);
        MixinContext context = context(owner, m);
        for (int remaining = 2; remaining >= 0; remaining--) {
            apply(owner, m, context, parameters, 0, 0);
            equal(remaining, m.visibleParameterAnnotations.length, "visible shrinking array");
            equal(remaining, m.invisibleParameterAnnotations.length, "invisible shrinking array");
            equal(remaining, m.visibleAnnotableParameterCount, "visible shrinking count");
            equal(remaining, m.invisibleAnnotableParameterCount, "invisible shrinking count");
        }
        rewriteDescriptor(m, parameters);
        equal("()V", m.desc, "zero descriptor");
        MethodNode reread = roundTrip(owner);
        check(reread.visibleParameterAnnotations == null, "zero visible omitted on wire");
        check(reread.invisibleParameterAnnotations == null, "zero invisible omitted on wire");
        equal(0, reread.visibleAnnotableParameterCount, "zero visible count");
        equal(0, reread.invisibleAnnotableParameterCount, "zero invisible count");
    }

    private static void noAnnotations() {
        MethodNode m = fixture(3, 0, false);
        ClassNode owner = owner(m);
        List<Type> parameters = parameters(m);
        apply(owner, m, context(owner, m), parameters, 1, 0);
        rewriteDescriptor(m, parameters);
        check(m.visibleParameterAnnotations == null && m.invisibleParameterAnnotations == null, "null arrays retained");
        equal(0, m.visibleAnnotableParameterCount, "null visible count");
        equal(0, m.invisibleAnnotableParameterCount, "null invisible count");
        MethodNode reread = roundTrip(owner);
        check(reread.visibleParameterAnnotations == null && reread.invisibleParameterAnnotations == null, "null arrays roundtrip");
    }

    private static void helperOnly() {
        MethodNode m = fixture(3, 3, true);
        List<ParameterNode> before = new ArrayList<>(m.parameters);
        RemoveParameterTransformer.validateParameterAnnotations(m, 3);
        RemoveParameterTransformer.removeParameterAnnotations(m, 1);
        equal(before, m.parameters, "helper does not own named parameters");
        equal(3, Type.getArgumentTypes(m.desc).length, "helper does not own descriptor");
        equal(2, m.visibleAnnotableParameterCount, "helper visible count");
        equal(2, m.invisibleAnnotableParameterCount, "helper invisible count");
        equal(2, value(m.visibleParameterAnnotations[1].getFirst(), "id"), "helper visible placement");
        equal(2, value(m.invisibleParameterAnnotations[1].getFirst(), "id"), "helper invisible placement");
    }

    private static void unchanged() {
        MethodNode m = fixture(3, 3, true);
        ClassNode owner = owner(m);
        byte[] before = bytes(owner);
        List<AnnotationNode>[] v = m.visibleParameterAnnotations, i = m.invisibleParameterAnnotations;
        RemoveParameterTransformer.validateParameterAnnotations(m, 3);
        equal(PatchResult.PASS, new TransformParameters(List.of(), false).apply(context(owner, m)), "empty transform pass");
        check(Arrays.equals(before, bytes(owner)), "validation/no-op class bytes unchanged");
        check(v == m.visibleParameterAnnotations && i == m.invisibleParameterAnnotations, "validation/no-op array identities unchanged");
    }

    private static void unchangedLithium(Path jar) throws Exception {
        ClassNode node = originalLithium(jar);
        byte[] before = bytes(node);
        for (MethodNode m : node.methods) RemoveParameterTransformer.validateParameterAnnotations(m, Type.getArgumentTypes(m.desc).length);
        check(Arrays.equals(before, bytes(node)), "whole Lithium class byte-identical before/after validation (ASM-normalized baseline)");
    }

    private static void unchangedImplicit() {
        MethodNode m = fixture(3, 3, false);
        ClassNode owner = owner(m);
        byte[] before = bytes(owner);
        RemoveParameterTransformer.validateParameterAnnotations(m, 3);
        check(Arrays.equals(before, bytes(owner)), "implicit count validation bytes unchanged");
        equal(0, m.visibleAnnotableParameterCount, "implicit visible count remains zero");
        equal(0, m.invisibleAnnotableParameterCount, "implicit invisible count remains zero");
    }

    private static void localVariables(boolean isStatic) {
        MethodNode m = fixture(4, 3, true);
        m.access = Opcodes.ACC_PUBLIC | (isStatic ? Opcodes.ACC_STATIC : 0);
        m.desc = "(JIDLjava/lang/String;)V";
        LabelNode start = new LabelNode(), end = new LabelNode();
        m.instructions.add(start);
        VarInsnNode load = new VarInsnNode(Opcodes.ALOAD, isStatic ? 5 : 6);
        m.instructions.add(load);
        m.instructions.add(new InsnNode(Opcodes.POP));
        m.instructions.add(new InsnNode(Opcodes.RETURN));
        m.instructions.add(end);
        int slot = isStatic ? 0 : 1;
        if (!isStatic) m.localVariables.add(new LocalVariableNode("this", "Lregression/Fixture;", null, start, end, 0));
        Type[] types = Type.getArgumentTypes(m.desc);
        for (int i = 0; i < types.length; i++) {
            m.localVariables.add(new LocalVariableNode("p" + i, types[i].getDescriptor(), null, start, end, slot));
            slot += types[i].getSize();
        }
        m.maxStack = 1;
        m.maxLocals = slot;
        ClassNode owner = owner(m);
        List<Type> parameters = parameters(m);
        apply(owner, m, context(owner, m), parameters, 0, 2);
        rewriteDescriptor(m, parameters);
        equal("(JILjava/lang/String;)V", m.desc, "wide removal descriptor");
        equal(isStatic ? 3 : 4, load.var, "wide removal local instruction shifted by two slots");
        check(m.localVariables.stream().noneMatch(l -> l.name.equals("p2")), "removed local eliminated");
        equal(isStatic ? 3 : 4, m.localVariables.stream().filter(l -> l.name.equals("p3")).findFirst().orElseThrow().index, "remaining local shifted by two slots");
        equal(3, value(m.visibleParameterAnnotations[2].getFirst(), "id"), "wide removal annotation uses descriptor coordinate");
        roundTrip(owner);
    }

    private static void rejectLayout(boolean visible, String kind) {
        MethodNode m = fixture(3, 3, true);
        // Give the method a genuine local and instruction referring to the to-be-
        // removed argument: validating late would corrupt these before rejection.
        m.access = Opcodes.ACC_PUBLIC;
        LabelNode start = new LabelNode(), end = new LabelNode();
        VarInsnNode load = new VarInsnNode(Opcodes.ILOAD, 1);
        m.instructions.add(start);
        m.instructions.add(load);
        m.instructions.add(new InsnNode(Opcodes.POP));
        m.instructions.add(new InsnNode(Opcodes.RETURN));
        m.instructions.add(end);
        LocalVariableNode local = new LocalVariableNode("p0", "I", null, start, end, 1);
        m.localVariables.add(local);
        m.maxStack = 1;
        m.maxLocals = 4;
        List<AnnotationNode>[] a = visible ? m.visibleParameterAnnotations : m.invisibleParameterAnnotations;
        int count = 3;
        switch (kind) {
            case "reduced-count" -> count = 2;
            case "oversized-count" -> count = 4;
            case "negative-count" -> count = -1;
            case "short-array" -> a = Arrays.copyOf(a, 2);
            case "long-array" -> a = Arrays.copyOf(a, 4);
            default -> throw new AssertionError(kind);
        }
        if (visible) { m.visibleParameterAnnotations = a; m.visibleAnnotableParameterCount = count; }
        else { m.invisibleParameterAnnotations = a; m.invisibleAnnotableParameterCount = count; }
        ClassNode owner = owner(m);
        // MixinContext.copyMethod itself uses ASM's visitor; construct before invalid
        // counts are supplied so a failure is unambiguously from the transformer.
        MethodNode pristine = fixture(3, 3, true);
        MixinContext context = context(owner(pristine), pristine);
        List<Type> parameters = parameters(m);
        List<Type> beforeTypes = new ArrayList<>(parameters);
        List<ParameterNode> beforeNames = new ArrayList<>(m.parameters);
        List<AnnotationNode>[] beforeV = m.visibleParameterAnnotations, beforeI = m.invisibleParameterAnnotations;
        int beforeVC = m.visibleAnnotableParameterCount, beforeIC = m.invisibleAnnotableParameterCount;
        String beforeDesc = m.desc;
        // Some intentionally illegal counts cannot be serialized by ASM. Layouts
        // with ordinary wire counts can be compared byte-for-byte as well.
        boolean serializable = !kind.equals("oversized-count") && !kind.equals("negative-count");
        byte[] beforeBytes = serializable ? bytes(owner) : null;
        try {
            new RemoveParameterTransformer(0).apply(owner, m, context, parameters, 0);
            throw new AssertionError("ambiguous layout was accepted");
        } catch (IllegalArgumentException expected) {
            check(expected.getMessage().contains("non-descriptor-coordinate"), "specific layout rejection");
        }
        equal(beforeTypes, parameters, "rejected parameter types unchanged");
        equal(beforeNames, m.parameters, "rejected parameter names unchanged");
        equal(beforeDesc, m.desc, "rejected descriptor unchanged");
        check(beforeV == m.visibleParameterAnnotations && beforeI == m.invisibleParameterAnnotations, "rejected annotation array identities unchanged");
        equal(beforeVC, m.visibleAnnotableParameterCount, "rejected visible count unchanged");
        equal(beforeIC, m.invisibleAnnotableParameterCount, "rejected invisible count unchanged");
        equal(List.of(local), m.localVariables, "rejected local table unchanged");
        equal(1, local.index, "rejected local index unchanged");
        equal(1, load.var, "rejected local instruction unchanged");
        if (serializable) check(Arrays.equals(beforeBytes, bytes(owner)), "rejected fixture byte-identical");
    }

    private static void staleDescriptor() {
        MethodNode m = fixture(3, 3, true);
        ClassNode owner = owner(m);
        List<Type> parameters = parameters(m);
        MixinContext context = context(owner, m);
        apply(owner, m, context, parameters, 0, 0);
        equal(3, Type.getArgumentTypes(m.desc).length, "descriptor deliberately stale");
        equal(2, parameters.size(), "live parameter list shortened");
        // A second removal must validate against the live list, not the descriptor.
        apply(owner, m, context, parameters, 1, 0);
        rewriteDescriptor(m, parameters);
        equal(1, m.invisibleAnnotableParameterCount, "second removal count");
        equal(1, value(roundTrip(owner).invisibleParameterAnnotations[0].getFirst(), "id"), "second removal retained original middle");
    }

    private static MethodNode fixture(int count, int visibility, boolean explicit) {
        MethodNode m = new MethodNode(Opcodes.ACC_PUBLIC | Opcodes.ACC_ABSTRACT, "handler", "(" + "I".repeat(count) + ")V", null, null);
        m.parameters = new ArrayList<>();
        m.localVariables = new ArrayList<>();
        for (int i = 0; i < count; i++) m.parameters.add(new ParameterNode("p" + i, i % 2 == 0 ? Opcodes.ACC_FINAL : 0));
        if ((visibility & 1) != 0) { m.visibleParameterAnnotations = annotations(count, "Lregression/Visible;"); m.visibleAnnotableParameterCount = explicit ? count : 0; }
        if ((visibility & 2) != 0) { m.invisibleParameterAnnotations = annotations(count, "Lregression/Invisible;"); m.invisibleAnnotableParameterCount = explicit ? count : 0; }
        return m;
    }

    @SuppressWarnings("unchecked")
    private static List<AnnotationNode>[] annotations(int count, String desc) {
        List<AnnotationNode>[] result = (List<AnnotationNode>[]) new List<?>[count];
        for (int i = 0; i < count; i++) {
            AnnotationNode a = new AnnotationNode(desc);
            a.visit("id", i);
            a.visit("name", "parameter-" + i);
            result[i] = new ArrayList<>(List.of(a));
        }
        return result;
    }

    private static List<AnnotationNode>[] cloneAnnotations(List<AnnotationNode>[] source) {
        List<AnnotationNode>[] result = source.clone();
        for (int i = 0; i < source.length; i++) {
            if (source[i] == null) continue;
            result[i] = new ArrayList<>();
            for (AnnotationNode a : source[i]) {
                AnnotationNode copy = new AnnotationNode(a.desc);
                a.accept(copy);
                result[i].add(copy);
            }
        }
        return result;
    }

    private static Object value(AnnotationNode annotation, String name) {
        for (int i = 0; i < annotation.values.size(); i += 2) if (annotation.values.get(i).equals(name)) return annotation.values.get(i + 1);
        throw new AssertionError("Missing annotation field " + name);
    }

    private static void checkRetained(List<AnnotationNode>[] after, List<AnnotationNode>[] before, int target, String label) {
        if (before == null) { check(after == null, label + " remains null"); return; }
        equal(before.length - 1, after.length, label + " array length");
        for (int i = 0; i < after.length; i++) check(after[i] == before[i < target ? i : i + 1], label + " retained list identity " + i);
    }

    private static ClassNode owner(MethodNode method) {
        ClassNode owner = new ClassNode();
        owner.version = Opcodes.V21;
        owner.access = Opcodes.ACC_PUBLIC | Opcodes.ACC_ABSTRACT;
        owner.name = "regression/Fixture";
        owner.superName = "java/lang/Object";
        owner.methods.add(method);
        return owner;
    }

    private static MixinContext context(ClassNode owner, MethodNode method) {
        List<Type> targets = List.of(Type.getObjectType("java/lang/Object"));
        return new MixinContext(null, PatchContext.create(owner, targets, null), new ClassTarget(targets, null), owner, method, null, null, Set.of());
    }

    private static List<Type> parameters(MethodNode m) { return new ArrayList<>(Arrays.asList(Type.getArgumentTypes(m.desc))); }

    private static void apply(ClassNode owner, MethodNode m, MixinContext context, List<Type> parameters, int index, int offset) {
        equal(PatchResult.COMPUTE_FRAMES, new RemoveParameterTransformer(index).apply(owner, m, context, parameters, offset), "actual apply result");
    }

    private static void rewriteDescriptor(MethodNode method, List<Type> parameters) {
        // TransformParameters.updateDescription normally performs this after all operations.
        method.desc = Type.getMethodDescriptor(Type.getReturnType(method.desc), parameters.toArray(Type[]::new));
        method.signature = null;
    }

    private static byte[] bytes(ClassNode node) {
        ClassWriter writer = new ClassWriter(0);
        node.accept(writer);
        return writer.toByteArray();
    }

    private static MethodNode roundTrip(ClassNode owner) {
        byte[] serialized = bytes(owner);
        ClassReader reader = new ClassReader(serialized);
        reader.accept(new CheckClassAdapter(new ClassWriter(0)), 0);
        ClassNode reread = new ClassNode();
        reader.accept(reread, 0);
        check(Arrays.equals(serialized, bytes(reread)), "serialization roundtrip bytes stable");
        return reread.methods.getFirst();
    }

    private static void check(boolean condition, String message) { checks++; if (!condition) throw new AssertionError(message); }
    private static void equal(Object expected, Object actual, String message) { check(Objects.equals(expected, actual), message + ": expected " + expected + ", actual " + actual); }
    private static void run(String label, Checked task) {
        tests++;
        try { task.run(); System.out.println("PASS: " + label); }
        catch (Throwable error) { failures++; System.err.println("FAIL: " + label + ": " + error); error.printStackTrace(System.err); }
    }
    @FunctionalInterface private interface Checked { void run() throws Exception; }
}
