package net.neoforged.fml.loading.diagnostic;

import cpw.mods.modlauncher.serviceapi.ILaunchPluginService;
import java.lang.reflect.InvocationTargetException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Label;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.Type;
import org.objectweb.asm.tree.AbstractInsnNode;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.FieldInsnNode;
import org.objectweb.asm.tree.InsnNode;
import org.objectweb.asm.tree.JumpInsnNode;
import org.objectweb.asm.tree.LdcInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import org.objectweb.asm.tree.TypeInsnNode;
import org.objectweb.asm.tree.VarInsnNode;

/** Defines only harmless generated fixtures; never loads real game, OSHI or GL classes. */
public final class CpuDescriptionSkipTest implements Opcodes {
    private static final String GLX = "com/mojang/blaze3d/platform/GLX";
    private static final String DEBUG = "com/mojang/blaze3d/platform/GlDebug";
    private static final String OSHI = "oshi/SystemInfo";
    private static final String CPU = "oshi/hardware/CentralProcessor";
    private static final String HAL = "oshi/hardware/HardwareAbstractionLayer";
    private static final String HW = "oshi/hardware/FixtureHardware";
    private static final String ID = CPU + "$ProcessorIdentifier";
    private static final Type TYPE = Type.getObjectType(GLX);
    private static int tests;

    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
    private static MethodNode method(ClassNode node, String name) {
        return node.methods.stream().filter(m -> m.name.equals(name)).findFirst().orElseThrow();
    }
    private static List<AbstractInsnNode> real(MethodNode method) {
        List<AbstractInsnNode> result = new ArrayList<>();
        for (AbstractInsnNode instruction : method.instructions) if (instruction.getOpcode() >= 0) result.add(instruction);
        return result;
    }
    private static byte[] bytes(ClassNode node) {
        ClassWriter writer = new ClassWriter(0); node.accept(writer); return writer.toByteArray();
    }
    private static Map<String, byte[]> otherMethods(ClassNode node) {
        Map<String, byte[]> result = new HashMap<>();
        for (MethodNode method : node.methods) if (!method.name.equals("_init")) {
            ClassWriter writer = new ClassWriter(0); writer.visit(V21, ACC_PUBLIC, GLX, null, "java/lang/Object", null);
            method.accept(writer); writer.visitEnd(); result.put(method.name + method.desc, writer.toByteArray());
        }
        return result;
    }
    private static ClassWriter writer(String name, String... interfaces) {
        ClassWriter writer = new ClassWriter(ClassWriter.COMPUTE_FRAMES | ClassWriter.COMPUTE_MAXS) {
            @Override protected String getCommonSuperClass(String left, String right) {
                if ((left.equals(CPU) && right.equals("java/lang/Throwable"))
                        || (right.equals(CPU) && left.equals("java/lang/Throwable"))) return "java/lang/Object";
                return super.getCommonSuperClass(left, right);
            }
        };
        writer.visit(V21, ACC_PUBLIC, name, null, "java/lang/Object", interfaces); return writer;
    }
    private static MethodVisitor start(ClassWriter writer, int access, String name, String descriptor) {
        MethodVisitor method = writer.visitMethod(access, name, descriptor, null, null); method.visitCode(); return method;
    }
    private static void end(MethodVisitor method) { method.visitMaxs(0, 0); method.visitEnd(); }
    private static void objectConstructor(ClassWriter writer) {
        MethodVisitor method = start(writer, ACC_PUBLIC, "<init>", "()V");
        method.visitVarInsn(ALOAD, 0); method.visitMethodInsn(INVOKESPECIAL, "java/lang/Object", "<init>", "()V", false);
        method.visitInsn(RETURN); end(method);
    }
    private static ClassNode fixture() {
        ClassWriter writer = writer(GLX);
        writer.visitField(ACC_PRIVATE | ACC_STATIC, "cpuInfo", "Ljava/lang/String;", null, null).visitEnd();
        MethodVisitor method = start(writer, ACC_PUBLIC | ACC_STATIC, "_init", "(IZ)V");
        Label from = new Label(), to = new Label(), handler = new Label(), tail = new Label();
        method.visitTryCatchBlock(from, to, handler, "java/lang/Throwable"); method.visitLabel(from);
        method.visitTypeInsn(NEW, OSHI); method.visitInsn(DUP);
        method.visitMethodInsn(INVOKESPECIAL, OSHI, "<init>", "()V", false);
        method.visitMethodInsn(INVOKEVIRTUAL, OSHI, "getHardware", "()L" + HAL + ";", false);
        method.visitMethodInsn(INVOKEINTERFACE, HAL, "getProcessor", "()L" + CPU + ";", true);
        method.visitVarInsn(ASTORE, 2);
        method.visitFieldInsn(GETSTATIC, "java/util/Locale", "ROOT", "Ljava/util/Locale;"); method.visitLdcInsn("%dx %s");
        method.visitInsn(ICONST_2); method.visitTypeInsn(ANEWARRAY, "java/lang/Object"); method.visitInsn(DUP);
        method.visitInsn(ICONST_0); method.visitVarInsn(ALOAD, 2);
        method.visitMethodInsn(INVOKEINTERFACE, CPU, "getLogicalProcessorCount", "()I", true);
        method.visitMethodInsn(INVOKESTATIC, "java/lang/Integer", "valueOf", "(I)Ljava/lang/Integer;", false);
        method.visitInsn(AASTORE); method.visitInsn(DUP); method.visitInsn(ICONST_1); method.visitVarInsn(ALOAD, 2);
        method.visitMethodInsn(INVOKEINTERFACE, CPU, "getProcessorIdentifier", "()L" + ID + ";", true);
        method.visitMethodInsn(INVOKEVIRTUAL, ID, "getName", "()Ljava/lang/String;", false); method.visitInsn(AASTORE);
        method.visitMethodInsn(INVOKESTATIC, "java/lang/String", "format", "(Ljava/util/Locale;Ljava/lang/String;[Ljava/lang/Object;)Ljava/lang/String;", false);
        method.visitLdcInsn("\\s+"); method.visitLdcInsn(" ");
        method.visitMethodInsn(INVOKEVIRTUAL, "java/lang/String", "replaceAll", "(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;", false);
        method.visitFieldInsn(PUTSTATIC, GLX, "cpuInfo", "Ljava/lang/String;"); method.visitLabel(to);
        method.visitJumpInsn(GOTO, tail); method.visitLabel(handler); method.visitVarInsn(ASTORE, 2); method.visitLabel(tail);
        method.visitVarInsn(ILOAD, 0); method.visitVarInsn(ILOAD, 1);
        method.visitMethodInsn(INVOKESTATIC, DEBUG, "enableDebugCallback", "(IZ)V", false); method.visitInsn(RETURN); end(method);
        method = start(writer, ACC_PUBLIC | ACC_STATIC, "_getCpuInfo", "()Ljava/lang/String;");
        Label present = new Label(), done = new Label();
        method.visitFieldInsn(GETSTATIC, GLX, "cpuInfo", "Ljava/lang/String;"); method.visitJumpInsn(IFNONNULL, present);
        method.visitLdcInsn("<unknown>"); method.visitJumpInsn(GOTO, done); method.visitLabel(present);
        method.visitFieldInsn(GETSTATIC, GLX, "cpuInfo", "Ljava/lang/String;"); method.visitLabel(done); method.visitInsn(ARETURN); end(method);
        method = start(writer, ACC_PUBLIC | ACC_STATIC, "unrelated", "()I"); method.visitIntInsn(BIPUSH, 23); method.visitInsn(IRETURN); end(method);
        writer.visitEnd(); ClassNode node = new ClassNode(); new ClassReader(writer.toByteArray()).accept(node, 0); return node;
    }
    private static byte[] iface(String name, String[][] methods) {
        ClassWriter writer = new ClassWriter(0); writer.visit(V21, ACC_PUBLIC | ACC_INTERFACE | ACC_ABSTRACT, name, null, "java/lang/Object", null);
        for (String[] row : methods) writer.visitMethod(ACC_PUBLIC | ACC_ABSTRACT, row[0], row[1], null, null).visitEnd();
        writer.visitEnd(); return writer.toByteArray();
    }
    private static Map<String, byte[]> stubs() {
        Map<String, byte[]> definitions = new HashMap<>();
        definitions.put(HAL, iface(HAL, new String[][]{{"getProcessor", "()L" + CPU + ";"}}));
        definitions.put(CPU, iface(CPU, new String[][]{{"getLogicalProcessorCount", "()I"}, {"getProcessorIdentifier", "()L" + ID + ";"}}));
        ClassWriter writer = writer(ID); objectConstructor(writer);
        MethodVisitor method = start(writer, ACC_PUBLIC, "getName", "()Ljava/lang/String;"); method.visitLdcInsn("fixture  CPU"); method.visitInsn(ARETURN); end(method);
        writer.visitEnd(); definitions.put(ID, writer.toByteArray());
        writer = writer(HW, HAL, CPU); objectConstructor(writer);
        method = start(writer, ACC_PUBLIC, "getProcessor", "()L" + CPU + ";"); method.visitVarInsn(ALOAD, 0); method.visitInsn(ARETURN); end(method);
        method = start(writer, ACC_PUBLIC, "getLogicalProcessorCount", "()I"); method.visitIntInsn(BIPUSH, 8); method.visitInsn(IRETURN); end(method);
        method = start(writer, ACC_PUBLIC, "getProcessorIdentifier", "()L" + ID + ";"); method.visitTypeInsn(NEW, ID); method.visitInsn(DUP);
        method.visitMethodInsn(INVOKESPECIAL, ID, "<init>", "()V", false); method.visitInsn(ARETURN); end(method);
        writer.visitEnd(); definitions.put(HW, writer.toByteArray());
        writer = writer(OSHI); writer.visitField(ACC_PUBLIC | ACC_STATIC, "created", "I", null, null).visitEnd();
        writer.visitField(ACC_PUBLIC | ACC_STATIC, "fail", "Z", null, null).visitEnd();
        method = start(writer, ACC_PUBLIC, "<init>", "()V"); method.visitVarInsn(ALOAD, 0);
        method.visitMethodInsn(INVOKESPECIAL, "java/lang/Object", "<init>", "()V", false);
        method.visitFieldInsn(GETSTATIC, OSHI, "created", "I"); method.visitInsn(ICONST_1); method.visitInsn(IADD); method.visitFieldInsn(PUTSTATIC, OSHI, "created", "I");
        Label good = new Label(); method.visitFieldInsn(GETSTATIC, OSHI, "fail", "Z"); method.visitJumpInsn(IFEQ, good);
        method.visitTypeInsn(NEW, "java/lang/Error"); method.visitInsn(DUP); method.visitMethodInsn(INVOKESPECIAL, "java/lang/Error", "<init>", "()V", false); method.visitInsn(ATHROW);
        method.visitLabel(good); method.visitInsn(RETURN); end(method);
        method = start(writer, ACC_PUBLIC, "getHardware", "()L" + HAL + ";"); method.visitTypeInsn(NEW, HW); method.visitInsn(DUP);
        method.visitMethodInsn(INVOKESPECIAL, HW, "<init>", "()V", false); method.visitInsn(ARETURN); end(method);
        writer.visitEnd(); definitions.put(OSHI, writer.toByteArray());
        writer = writer(DEBUG);
        for (String field : new String[]{"calls", "lastInt"}) writer.visitField(ACC_PUBLIC | ACC_STATIC, field, "I", null, null).visitEnd();
        for (String field : new String[]{"lastBool", "fail"}) writer.visitField(ACC_PUBLIC | ACC_STATIC, field, "Z", null, null).visitEnd();
        method = start(writer, ACC_PUBLIC | ACC_STATIC, "enableDebugCallback", "(IZ)V");
        method.visitVarInsn(ILOAD, 0); method.visitFieldInsn(PUTSTATIC, DEBUG, "lastInt", "I");
        method.visitVarInsn(ILOAD, 1); method.visitFieldInsn(PUTSTATIC, DEBUG, "lastBool", "Z");
        method.visitFieldInsn(GETSTATIC, DEBUG, "calls", "I"); method.visitInsn(ICONST_1); method.visitInsn(IADD); method.visitFieldInsn(PUTSTATIC, DEBUG, "calls", "I");
        good = new Label(); method.visitFieldInsn(GETSTATIC, DEBUG, "fail", "Z"); method.visitJumpInsn(IFEQ, good);
        method.visitTypeInsn(NEW, "java/lang/IllegalStateException"); method.visitInsn(DUP);
        method.visitMethodInsn(INVOKESPECIAL, "java/lang/IllegalStateException", "<init>", "()V", false); method.visitInsn(ATHROW);
        method.visitLabel(good); method.visitInsn(RETURN); end(method); writer.visitEnd(); definitions.put(DEBUG, writer.toByteArray());
        return definitions;
    }
    private static final class FixtureLoader extends ClassLoader {
        private final Map<String, byte[]> definitions = stubs();
        FixtureLoader(byte[] target) { definitions.put(GLX, target); }
        @Override protected Class<?> findClass(String name) throws ClassNotFoundException {
            byte[] data = definitions.get(name.replace('.', '/'));
            if (data == null) throw new ClassNotFoundException("fixture class absent");
            return defineClass(name, data, 0, data.length);
        }
    }
    private static void behavior(byte[] target, boolean skipped) throws Exception {
        FixtureLoader loader = new FixtureLoader(target);
        Class<?> type = loader.loadClass(GLX.replace('/', '.')), debug = loader.loadClass(DEBUG.replace('/', '.')), oshi = loader.loadClass(OSHI.replace('/', '.'));
        var init = type.getMethod("_init", int.class, boolean.class);
        check(type.getMethod("_getCpuInfo").invoke(null).equals("<unknown>"), "initial_placeholder");
        for (int i = 0; i < 2; i++) {
            int value = i == 0 ? 7 : -12; boolean flag = i != 0; init.invoke(null, value, flag);
            check(debug.getField("calls").getInt(null) == i + 1 && debug.getField("lastInt").getInt(null) == value
                    && debug.getField("lastBool").getBoolean(null) == flag, "callback_arguments_and_count_preserved");
            check(type.getMethod("_getCpuInfo").invoke(null).equals(skipped ? "<unknown>" : "8x fixture CPU"), "description_only_changed");
        }
        oshi.getField("fail").setBoolean(null, true); init.invoke(null, 23, false);
        check(debug.getField("calls").getInt(null) == 3 && debug.getField("lastInt").getInt(null) == 23, "cpu_exception_never_skips_callback");
        debug.getField("fail").setBoolean(null, true);
        try { init.invoke(null, 31, true); throw new AssertionError("callback_exception_expected"); }
        catch (InvocationTargetException expected) { check(expected.getCause() instanceof IllegalStateException, "callback_exception_not_swallowed"); }
        check(debug.getField("calls").getInt(null) == 4 && debug.getField("lastInt").getInt(null) == 31
                && debug.getField("lastBool").getBoolean(null), "throwing_callback_arguments_retained");
        check(oshi.getField("created").getInt(null) == (skipped ? 0 : 4), "inventory_only_skip");
        check(type.getMethod("unrelated").invoke(null).equals(23), "unrelated_behavior_retained"); tests++;
    }
    private static void reject(String label, Consumer<ClassNode> mutation) {
        ClassNode node = fixture(); mutation.accept(node); byte[] before = bytes(node);
        try { new HardwareInventorySkipLaunchPlugin().processClassWithFlags(ILaunchPluginService.Phase.AFTER, node, TYPE, "classloading"); throw new AssertionError(label); }
        catch (HardwareInventorySkipLaunchPlugin.Refused expected) {
            check(expected.getStackTrace().length == 0 && expected.getCause() == null, "fixed_refusal");
            check(Arrays.equals(before, bytes(node)), "no_partial_mutation");
        }
        tests++;
    }
    public static void main(String[] args) throws Exception {
        ClassNode node = fixture(); byte[] before = bytes(node); behavior(before, false);
        var plugin = new HardwareInventorySkipLaunchPlugin();
        check(plugin.handlesClass(TYPE, false, "classloading").equals(java.util.EnumSet.of(ILaunchPluginService.Phase.AFTER)), "classloading_after");
        check(plugin.handlesClass(TYPE, true, "classloading").isEmpty() && plugin.handlesClass(TYPE, false).isEmpty(), "empty_or_unspecified_not_selected");
        for (String reason : new String[]{"computing_frames", "other-plugin", ""}) {
            check(plugin.handlesClass(TYPE, false, reason).isEmpty(), "reason_not_selected");
            check(plugin.processClassWithFlags(ILaunchPluginService.Phase.AFTER, node, TYPE, reason) == 0 && Arrays.equals(before, bytes(node)), "reason_no_mutation"); tests++;
        }
        var originals = otherMethods(node); var tail = new ArrayList<>(real(method(node, "_init")).subList(29, 33));
        check(plugin.processClassWithFlags(ILaunchPluginService.Phase.AFTER, node, TYPE, "classloading") == ILaunchPluginService.ComputeFlags.SIMPLE_REWRITE, "simple_rewrite");
        List<AbstractInsnNode> after = real(method(node, "_init"));
        check(after.size() == 6, "only_placeholder_and_original_tail");
        for (int i = 0; i < 4; i++) check(after.get(i + 2) == tail.get(i), "original_tail_objects_retained");
        for (var row : otherMethods(node).entrySet()) check(Arrays.equals(originals.get(row.getKey()), row.getValue()), "other_methods_exact");
        behavior(bytes(node), true);
        byte[] transformed = bytes(node);
        try { plugin.processClassWithFlags(ILaunchPluginService.Phase.AFTER, node, TYPE, "classloading"); throw new AssertionError("repeated_target"); }
        catch (HardwareInventorySkipLaunchPlugin.Refused expected) { check(Arrays.equals(transformed, bytes(node)), "repeated_no_mutation"); tests++; }
        plugin.processClassWithFlags(ILaunchPluginService.Phase.AFTER, HardwareInventorySkipTest.fixture(), Type.getObjectType("net/minecraft/SystemReport"), "classloading"); tests++;
        plugin = new HardwareInventorySkipLaunchPlugin();
        plugin.processClassWithFlags(ILaunchPluginService.Phase.AFTER, HardwareInventorySkipTest.fixture(), Type.getObjectType("net/minecraft/SystemReport"), "classloading");
        plugin.processClassWithFlags(ILaunchPluginService.Phase.AFTER, fixture(), TYPE, "classloading"); tests++;
        reject("version", n -> n.version = V17);
        reject("class_name", n -> n.name = "other/GLX");
        reject("missing_method", n -> n.methods.remove(method(n, "_init")));
        reject("duplicate_method", n -> n.methods.add(new MethodNode(ACC_PUBLIC | ACC_STATIC, "_init", "()V", null, null)));
        reject("method_access", n -> method(n, "_init").access = ACC_PUBLIC);
        reject("method_descriptor", n -> method(n, "_init").desc = "(II)V");
        reject("method_max_stack", n -> method(n, "_init").maxStack++);
        reject("method_max_locals", n -> method(n, "_init").maxLocals++);
        reject("extra_instruction", n -> method(n, "_init").instructions.insert(new InsnNode(NOP)));
        reject("oshi_owner", n -> ((TypeInsnNode)real(method(n, "_init")).get(0)).desc = "other/SystemInfo");
        reject("processor_call", n -> ((MethodInsnNode)real(method(n, "_init")).get(4)).itf = false);
        reject("format_string", n -> ((LdcInsnNode)real(method(n, "_init")).get(7)).cst = "%s");
        reject("processor_slot", n -> ((VarInsnNode)real(method(n, "_init")).get(12)).var = 1);
        reject("field_target", n -> ((FieldInsnNode)real(method(n, "_init")).get(26)).name = "otherInfo");
        reject("goto_target", n -> ((JumpInsnNode)real(method(n, "_init")).get(27)).label = method(n, "_init").tryCatchBlocks.get(0).handler);
        reject("handler_type", n -> method(n, "_init").tryCatchBlocks.get(0).type = "java/lang/Exception");
        reject("handler_start", n -> method(n, "_init").tryCatchBlocks.get(0).start = method(n, "_init").tryCatchBlocks.get(0).end);
        reject("handler_end", n -> method(n, "_init").tryCatchBlocks.get(0).end = ((JumpInsnNode)real(method(n, "_init")).get(27)).label);
        reject("handler_target", n -> method(n, "_init").tryCatchBlocks.get(0).handler = ((JumpInsnNode)real(method(n, "_init")).get(27)).label);
        reject("extra_handler", n -> method(n, "_init").tryCatchBlocks.add(method(n, "_init").tryCatchBlocks.get(0)));
        reject("debug_arg", n -> ((VarInsnNode)real(method(n, "_init")).get(30)).var = 0);
        reject("debug_owner", n -> ((MethodInsnNode)real(method(n, "_init")).get(31)).owner = "other/Debug");
        reject("debug_method", n -> ((MethodInsnNode)real(method(n, "_init")).get(31)).name = "otherCallback");
        reject("debug_descriptor", n -> ((MethodInsnNode)real(method(n, "_init")).get(31)).desc = "(II)V");
        reject("field_access", n -> n.fields.get(0).access = ACC_PUBLIC | ACC_STATIC);
        reject("field_descriptor", n -> n.fields.get(0).desc = "Ljava/lang/Object;");
        reject("extra_field", n -> n.fields.add(n.fields.get(0)));
        reject("getter_placeholder", n -> ((LdcInsnNode)real(method(n, "_getCpuInfo")).get(2)).cst = "other");
        reject("getter_branch", n -> ((JumpInsnNode)real(method(n, "_getCpuInfo")).get(1)).label = ((JumpInsnNode)real(method(n, "_getCpuInfo")).get(3)).label);
        reject("extra_field_consumer", n -> method(n, "unrelated").instructions.insert(new FieldInsnNode(GETSTATIC, GLX, "cpuInfo", "Ljava/lang/String;")));
        ClassNode wrongPhase = fixture(); before = bytes(wrongPhase);
        try { new HardwareInventorySkipLaunchPlugin().processClassWithFlags(ILaunchPluginService.Phase.BEFORE, wrongPhase, TYPE, "classloading"); throw new AssertionError("phase"); }
        catch (HardwareInventorySkipLaunchPlugin.Refused expected) { check(Arrays.equals(before, bytes(wrongPhase)), "phase_no_mutation"); tests++; }
        System.out.println("PASS cpu_description_fixture tests=" + tests + " real_hardware=false real_game=false real_gl=false baseline_acceptance=false");
    }
}
