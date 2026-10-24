package net.neoforged.fml.loading.diagnostic;

import cpw.mods.modlauncher.serviceapi.ILaunchPluginService;
import java.util.ArrayList;
import java.util.EnumSet;
import java.util.List;
import org.objectweb.asm.Handle;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.Type;
import org.objectweb.asm.tree.AbstractInsnNode;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.FieldInsnNode;
import org.objectweb.asm.tree.FieldNode;
import org.objectweb.asm.tree.JumpInsnNode;
import org.objectweb.asm.tree.LabelNode;
import org.objectweb.asm.tree.InsnNode;
import org.objectweb.asm.tree.InvokeDynamicInsnNode;
import org.objectweb.asm.tree.LdcInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import org.objectweb.asm.tree.TypeInsnNode;
import org.objectweb.asm.tree.VarInsnNode;

/**
 * Separately named behavioral diagnostic, not baseline compatibility evidence.
 * Uses the existing ModLauncher SPI, never a javaagent or game-JAR replacement.
 * Skips the verified SystemReport hardware lambda and GLX CPU-description block.
 * The original GLX debug callback tail, arguments and exception behavior are retained.
 * Unknown shapes abort this diagnostic launch; they never fall through to probing.
 */
public final class HardwareInventorySkipLaunchPlugin implements ILaunchPluginService {
    private static final String OWNER = "net/minecraft/SystemReport";
    private static final String GLX = "com/mojang/blaze3d/platform/GLX";
    private static final String GLDEBUG = "com/mojang/blaze3d/platform/GlDebug";
    private static final String CPU = "oshi/hardware/CentralProcessor";
    private static final String CPU_PLACEHOLDER = "<unknown>";
    private static final String LAMBDA = "lambda$new$2";
    private static final String OSHI = "oshi/SystemInfo";
    private static final String METAFACTORY = "(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;"
            + "Ljava/lang/invoke/MethodType;Ljava/lang/invoke/MethodType;Ljava/lang/invoke/MethodHandle;"
            + "Ljava/lang/invoke/MethodType;)Ljava/lang/invoke/CallSite;";
    private boolean transformed;
    private boolean cpuTransformed;

    /** Fixed code only, no cause or stack. Never include input class/code/error data. */
    public static final class Refused extends RuntimeException {
        private static final long serialVersionUID = 1L;
        private Refused(String code) { super("hardware diagnostic refused: " + code, null, false, false); }
    }

    @Override public String name() { return "unified_hardware_inventory_skip_diagnostic"; }

    @Override public EnumSet<Phase> handlesClass(Type classType, boolean isEmpty) {
        return EnumSet.noneOf(Phase.class); // Never consume the one-shot on an unspecified reason.
    }

    @Override public EnumSet<Phase> handlesClass(Type classType, boolean isEmpty, String reason) {
        return "classloading".equals(reason) && !isEmpty && classType != null
                && (OWNER.equals(classType.getInternalName()) || GLX.equals(classType.getInternalName()))
                ? EnumSet.of(Phase.AFTER) : EnumSet.noneOf(Phase.class);
    }

    @Override public synchronized int processClassWithFlags(Phase phase, ClassNode node,
                                                          Type classType, String reason) {
        if (!"classloading".equals(reason) || classType == null) return ComputeFlags.NO_REWRITE;
        if (GLX.equals(classType.getInternalName())) return transformCpuDescription(phase, node);
        if (!OWNER.equals(classType.getInternalName())) return ComputeFlags.NO_REWRITE;
        require(phase == Phase.AFTER, "PHASE");
        require(!transformed, "REPEATED_TARGET");
        require(node != null && OWNER.equals(node.name) && node.version == Opcodes.V21
                && node.methods != null && node.methods.size() <= 1024, "CLASS_SHAPE");
        MethodNode target = null;
        MethodNode constructor = null;
        int targetCount = 0;
        int constructorCount = 0;
        for (MethodNode method : node.methods) {
            if (LAMBDA.equals(method.name)) { target = method; targetCount++; }
            if ("<init>".equals(method.name) && "()V".equals(method.desc)) {
                constructor = method; constructorCount++;
            }
        }
        require(targetCount == 1 && constructorCount == 1, "METHOD_COUNT");
        require(target.access == (Opcodes.ACC_PRIVATE | Opcodes.ACC_SYNTHETIC)
                && "()V".equals(target.desc) && target.signature == null
                && target.maxStack == 3 && target.maxLocals == 1
                && target.tryCatchBlocks.isEmpty()
                && (target.attrs == null || target.attrs.isEmpty()), "METHOD_SHAPE");
        List<AbstractInsnNode> body = realInstructions(target, 64);
        require(body.size() == 6 && aload0(body.get(0))
                && body.get(1) instanceof TypeInsnNode allocation
                && allocation.getOpcode() == Opcodes.NEW && OSHI.equals(allocation.desc)
                && body.get(2).getOpcode() == Opcodes.DUP
                && call(body.get(3), Opcodes.INVOKESPECIAL, OSHI, "<init>", "()V")
                && call(body.get(4), Opcodes.INVOKEVIRTUAL, OWNER, "putHardware", "(Loshi/SystemInfo;)V")
                && body.get(5).getOpcode() == Opcodes.RETURN, "LAMBDA_FINGERPRINT");
        require(constructor.access == Opcodes.ACC_PUBLIC && constructor.tryCatchBlocks.isEmpty(),
                "CONSTRUCTOR_SHAPE");
        List<AbstractInsnNode> ctor = realInstructions(constructor, 1024);
        int bindings = 0;
        int hardwareLabels = 0;
        for (int index = 0; index < ctor.size(); index++) {
            AbstractInsnNode instruction = ctor.get(index);
            if (instruction instanceof LdcInsnNode label && "hardware".equals(label.cst)) hardwareLabels++;
            if (instruction instanceof InvokeDynamicInsnNode dynamic && referencesTarget(dynamic)) {
                require(index >= 3 && index + 1 < ctor.size()
                        && aload0(ctor.get(index - 3))
                        && ctor.get(index - 2) instanceof LdcInsnNode label && "hardware".equals(label.cst)
                        && aload0(ctor.get(index - 1))
                        && lambdaFactory(dynamic)
                        && call(ctor.get(index + 1), Opcodes.INVOKEVIRTUAL, OWNER, "ignoreErrors",
                                "(Ljava/lang/String;Ljava/lang/Runnable;)V"), "WRAPPER_FINGERPRINT");
                bindings++;
            }
        }
        require(bindings == 1 && hardwareLabels == 1, "WRAPPER_COUNT");
        // No second use is allowed to broaden the skipped behavior beyond that wrapper.
        int allBindings = 0;
        for (MethodNode method : node.methods) {
            for (AbstractInsnNode instruction : realInstructions(method, 8192)) {
                if (instruction instanceof InvokeDynamicInsnNode dynamic && referencesTarget(dynamic)) allBindings++;
                require(!(instruction instanceof MethodInsnNode invocation
                        && OWNER.equals(invocation.owner) && LAMBDA.equals(invocation.name)), "EXTRA_LAMBDA_USE");
            }
        }
        require(allBindings == 1, "EXTRA_LAMBDA_BINDING");

        // Every check precedes mutation. Other method bodies/fields stay untouched.
        target.instructions.clear();
        target.instructions.add(new InsnNode(Opcodes.RETURN));
        target.tryCatchBlocks.clear();
        if (target.localVariables != null) target.localVariables.clear();
        if (target.visibleLocalVariableAnnotations != null) target.visibleLocalVariableAnnotations.clear();
        if (target.invisibleLocalVariableAnnotations != null) target.invisibleLocalVariableAnnotations.clear();
        target.maxStack = 0;
        target.maxLocals = 1;
        transformed = true;
        try {
            System.out.println("{\"kind\":\"hardware_inventory_skip_diagnostic\",\"state\":\"TRANSFORMED\","
                    + "\"diagnostic_only\":true,\"baseline_acceptance\":false}");
            require(!System.out.checkError(), "STATUS_OUTPUT");
        } catch (Throwable ignored) { throw new Refused("STATUS_OUTPUT"); }
        return ComputeFlags.SIMPLE_REWRITE;
    }

    private int transformCpuDescription(Phase phase, ClassNode node) {
        require(phase == Phase.AFTER, "CPU_PHASE");
        require(!cpuTransformed, "CPU_REPEATED_TARGET");
        require(node != null && GLX.equals(node.name) && node.version == Opcodes.V21
                && node.methods != null && node.methods.size() <= 1024
                && node.fields != null && node.fields.size() <= 1024, "CPU_CLASS_SHAPE");
        MethodNode target = null;
        MethodNode getter = null;
        int targets = 0;
        int getters = 0;
        int fields = 0;
        for (FieldNode field : node.fields) if ("cpuInfo".equals(field.name)) {
            fields++;
            require(field.access == (Opcodes.ACC_PRIVATE | Opcodes.ACC_STATIC)
                    && "Ljava/lang/String;".equals(field.desc) && field.value == null
                    && field.signature == null, "CPU_FIELD_SHAPE");
        }
        for (MethodNode method : node.methods) {
            if ("_init".equals(method.name)) { target = method; targets++; }
            if ("_getCpuInfo".equals(method.name)) { getter = method; getters++; }
        }
        require(targets == 1 && getters == 1 && fields == 1, "CPU_MEMBER_COUNT");
        require(target.access == (Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC)
                && "(IZ)V".equals(target.desc) && target.signature == null
                && target.maxStack == 6 && target.maxLocals == 3
                && target.tryCatchBlocks.size() == 1
                && (target.attrs == null || target.attrs.isEmpty()), "CPU_METHOD_SHAPE");
        List<AbstractInsnNode> body = realInstructions(target, 128);
        require(body.size() == 33
                && type(body.get(0), Opcodes.NEW, OSHI) && opcode(body.get(1), Opcodes.DUP)
                && call(body.get(2), Opcodes.INVOKESPECIAL, OSHI, "<init>", "()V")
                && call(body.get(3), Opcodes.INVOKEVIRTUAL, OSHI, "getHardware", "()Loshi/hardware/HardwareAbstractionLayer;")
                && interfaceCall(body.get(4), "oshi/hardware/HardwareAbstractionLayer", "getProcessor", "()L" + CPU + ";")
                && variable(body.get(5), Opcodes.ASTORE, 2)
                && field(body.get(6), Opcodes.GETSTATIC, "java/util/Locale", "ROOT", "Ljava/util/Locale;")
                && constant(body.get(7), "%dx %s") && opcode(body.get(8), Opcodes.ICONST_2)
                && type(body.get(9), Opcodes.ANEWARRAY, "java/lang/Object")
                && opcode(body.get(10), Opcodes.DUP) && opcode(body.get(11), Opcodes.ICONST_0)
                && variable(body.get(12), Opcodes.ALOAD, 2)
                && interfaceCall(body.get(13), CPU, "getLogicalProcessorCount", "()I")
                && call(body.get(14), Opcodes.INVOKESTATIC, "java/lang/Integer", "valueOf", "(I)Ljava/lang/Integer;")
                && opcode(body.get(15), Opcodes.AASTORE) && opcode(body.get(16), Opcodes.DUP)
                && opcode(body.get(17), Opcodes.ICONST_1) && variable(body.get(18), Opcodes.ALOAD, 2)
                && interfaceCall(body.get(19), CPU, "getProcessorIdentifier", "()L" + CPU + "$ProcessorIdentifier;")
                && call(body.get(20), Opcodes.INVOKEVIRTUAL, CPU + "$ProcessorIdentifier", "getName", "()Ljava/lang/String;")
                && opcode(body.get(21), Opcodes.AASTORE)
                && call(body.get(22), Opcodes.INVOKESTATIC, "java/lang/String", "format", "(Ljava/util/Locale;Ljava/lang/String;[Ljava/lang/Object;)Ljava/lang/String;")
                && constant(body.get(23), "\\s+") && constant(body.get(24), " ")
                && call(body.get(25), Opcodes.INVOKEVIRTUAL, "java/lang/String", "replaceAll", "(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;")
                && field(body.get(26), Opcodes.PUTSTATIC, GLX, "cpuInfo", "Ljava/lang/String;")
                && body.get(27) instanceof JumpInsnNode jump && jump.getOpcode() == Opcodes.GOTO
                && labelPosition(target, jump.label) == 29
                && variable(body.get(28), Opcodes.ASTORE, 2)
                && variable(body.get(29), Opcodes.ILOAD, 0) && variable(body.get(30), Opcodes.ILOAD, 1)
                && call(body.get(31), Opcodes.INVOKESTATIC, GLDEBUG, "enableDebugCallback", "(IZ)V")
                && opcode(body.get(32), Opcodes.RETURN), "CPU_FINGERPRINT");
        var handler = target.tryCatchBlocks.get(0);
        require("java/lang/Throwable".equals(handler.type)
                && labelPosition(target, handler.start) == 0 && labelPosition(target, handler.end) == 27
                && labelPosition(target, handler.handler) == 28
                && (handler.visibleTypeAnnotations == null || handler.visibleTypeAnnotations.isEmpty())
                && (handler.invisibleTypeAnnotations == null || handler.invisibleTypeAnnotations.isEmpty()), "CPU_HANDLER");
        require(getter.access == (Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC)
                && "()Ljava/lang/String;".equals(getter.desc) && getter.signature == null
                && getter.maxStack == 1 && getter.maxLocals == 0 && getter.tryCatchBlocks.isEmpty(), "CPU_GETTER_SHAPE");
        List<AbstractInsnNode> read = realInstructions(getter, 64);
        require(read.size() == 6 && field(read.get(0), Opcodes.GETSTATIC, GLX, "cpuInfo", "Ljava/lang/String;")
                && read.get(1) instanceof JumpInsnNode present && present.getOpcode() == Opcodes.IFNONNULL
                && labelPosition(getter, present.label) == 4 && constant(read.get(2), CPU_PLACEHOLDER)
                && read.get(3) instanceof JumpInsnNode end && end.getOpcode() == Opcodes.GOTO
                && labelPosition(getter, end.label) == 5
                && field(read.get(4), Opcodes.GETSTATIC, GLX, "cpuInfo", "Ljava/lang/String;")
                && opcode(read.get(5), Opcodes.ARETURN), "CPU_GETTER_FINGERPRINT");
        int references = 0;
        for (MethodNode method : node.methods) for (AbstractInsnNode instruction : realInstructions(method, 8192)) {
            if (instruction instanceof FieldInsnNode access && GLX.equals(access.owner) && "cpuInfo".equals(access.name)) {
                require(method == target || method == getter, "CPU_EXTRA_FIELD_USE");
                references++;
            }
        }
        require(references == 3, "CPU_FIELD_USE_COUNT");

        // Guarded CPU-only block and its dead handler are removed. Keep the exact
        // four original debug-tail instruction objects, arguments, order and call.
        List<AbstractInsnNode> tail = body.subList(29, 33);
        for (AbstractInsnNode instruction : tail) target.instructions.remove(instruction);
        target.instructions.clear();
        target.instructions.add(new LdcInsnNode(CPU_PLACEHOLDER));
        target.instructions.add(new FieldInsnNode(Opcodes.PUTSTATIC, GLX, "cpuInfo", "Ljava/lang/String;"));
        for (AbstractInsnNode instruction : tail) target.instructions.add(instruction);
        target.tryCatchBlocks.clear();
        if (target.localVariables != null) target.localVariables.clear();
        if (target.visibleLocalVariableAnnotations != null) target.visibleLocalVariableAnnotations.clear();
        if (target.invisibleLocalVariableAnnotations != null) target.invisibleLocalVariableAnnotations.clear();
        target.maxStack = 2;
        target.maxLocals = 2;
        cpuTransformed = true;
        try {
            System.out.println("{\"kind\":\"cpu_description_skip_diagnostic\",\"state\":\"TRANSFORMED\","
                    + "\"diagnostic_only\":true,\"baseline_acceptance\":false}");
            require(!System.out.checkError(), "CPU_STATUS_OUTPUT");
        } catch (Throwable ignored) { throw new Refused("CPU_STATUS_OUTPUT"); }
        return ComputeFlags.SIMPLE_REWRITE;
    }

    private static int labelPosition(MethodNode method, LabelNode label) {
        int index = 0;
        for (AbstractInsnNode instruction : method.instructions) {
            if (instruction == label) return index;
            if (instruction.getOpcode() >= 0) index++;
        }
        return -1;
    }
    private static boolean opcode(AbstractInsnNode node, int opcode) {
        return node instanceof InsnNode && node.getOpcode() == opcode;
    }
    private static boolean variable(AbstractInsnNode node, int opcode, int slot) {
        return node instanceof VarInsnNode var && var.getOpcode() == opcode && var.var == slot;
    }
    private static boolean constant(AbstractInsnNode node, String value) {
        return node instanceof LdcInsnNode constant && value.equals(constant.cst);
    }
    private static boolean type(AbstractInsnNode node, int opcode, String name) {
        return node instanceof TypeInsnNode type && type.getOpcode() == opcode && name.equals(type.desc);
    }
    private static boolean field(AbstractInsnNode node, int opcode, String owner, String name, String descriptor) {
        return node instanceof FieldInsnNode field && field.getOpcode() == opcode
                && owner.equals(field.owner) && name.equals(field.name) && descriptor.equals(field.desc);
    }
    private static boolean interfaceCall(AbstractInsnNode node, String owner, String name, String descriptor) {
        return node instanceof MethodInsnNode call && call.getOpcode() == Opcodes.INVOKEINTERFACE && call.itf
                && owner.equals(call.owner) && name.equals(call.name) && descriptor.equals(call.desc);
    }

    private static List<AbstractInsnNode> realInstructions(MethodNode method, int bound) {
        require(method.instructions != null && method.instructions.size() <= bound, "INSTRUCTION_BOUND");
        List<AbstractInsnNode> result = new ArrayList<>();
        for (AbstractInsnNode instruction : method.instructions)
            if (instruction.getOpcode() >= 0) result.add(instruction);
        return result;
    }
    private static boolean aload0(AbstractInsnNode node) {
        return node instanceof VarInsnNode var && var.getOpcode() == Opcodes.ALOAD && var.var == 0;
    }
    private static boolean call(AbstractInsnNode node, int opcode, String owner, String name, String descriptor) {
        return node instanceof MethodInsnNode call && call.getOpcode() == opcode && !call.itf
                && owner.equals(call.owner) && name.equals(call.name) && descriptor.equals(call.desc);
    }
    private static boolean referencesTarget(InvokeDynamicInsnNode dynamic) {
        for (Object argument : dynamic.bsmArgs)
            if (argument instanceof Handle handle && OWNER.equals(handle.getOwner())
                    && LAMBDA.equals(handle.getName())) return true;
        return false;
    }
    private static boolean lambdaFactory(InvokeDynamicInsnNode dynamic) {
        Handle bootstrap = dynamic.bsm;
        return "run".equals(dynamic.name) && ("(L" + OWNER + ";)Ljava/lang/Runnable;").equals(dynamic.desc)
                && bootstrap.getTag() == Opcodes.H_INVOKESTATIC && !bootstrap.isInterface()
                && "java/lang/invoke/LambdaMetafactory".equals(bootstrap.getOwner())
                && "metafactory".equals(bootstrap.getName()) && METAFACTORY.equals(bootstrap.getDesc())
                && dynamic.bsmArgs.length == 3 && Type.getMethodType("()V").equals(dynamic.bsmArgs[0])
                && dynamic.bsmArgs[1] instanceof Handle handle
                && handle.getTag() == Opcodes.H_INVOKEVIRTUAL && !handle.isInterface()
                && OWNER.equals(handle.getOwner()) && LAMBDA.equals(handle.getName())
                && "()V".equals(handle.getDesc()) && Type.getMethodType("()V").equals(dynamic.bsmArgs[2]);
    }
    private static void require(boolean condition, String code) {
        if (!condition) throw new Refused(code);
    }
}
