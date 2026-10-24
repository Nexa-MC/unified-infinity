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
 * Replaces only the verified SystemReport constructor hardware lambda with RETURN.
 * Unknown shapes abort this diagnostic launch; they never fall through to probing.
 */
public final class HardwareInventorySkipLaunchPlugin implements ILaunchPluginService {
    private static final String OWNER = "net/minecraft/SystemReport";
    private static final String LAMBDA = "lambda$new$2";
    private static final String OSHI = "oshi/SystemInfo";
    private static final String METAFACTORY = "(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;"
            + "Ljava/lang/invoke/MethodType;Ljava/lang/invoke/MethodType;Ljava/lang/invoke/MethodHandle;"
            + "Ljava/lang/invoke/MethodType;)Ljava/lang/invoke/CallSite;";
    private boolean transformed;

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
                && OWNER.equals(classType.getInternalName())
                ? EnumSet.of(Phase.AFTER) : EnumSet.noneOf(Phase.class);
    }

    @Override public synchronized int processClassWithFlags(Phase phase, ClassNode node,
                                                          Type classType, String reason) {
        if (!"classloading".equals(reason) || classType == null
                || !OWNER.equals(classType.getInternalName())) return ComputeFlags.NO_REWRITE;
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
