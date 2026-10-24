package net.neoforged.fml.loading.diagnostic;

import cpw.mods.modlauncher.serviceapi.ILaunchPluginService;
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;
import java.util.function.Consumer;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Handle;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.Type;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.InsnNode;
import org.objectweb.asm.tree.InvokeDynamicInsnNode;
import org.objectweb.asm.tree.LabelNode;
import org.objectweb.asm.tree.LdcInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import org.objectweb.asm.tree.TryCatchBlockNode;
import org.objectweb.asm.tree.TypeInsnNode;
import org.objectweb.asm.tree.VarInsnNode;

/** Behavior fixture only: OSHI is an in-memory harmless counter stub, never real hardware. */
public final class HardwareInventorySkipTest {
    private static final String OWNER = "net/minecraft/SystemReport";
    private static final String NAME = "lambda$new$2";
    private static final Type TYPE = Type.getObjectType(OWNER);
    private static final Handle BSM = new Handle(Opcodes.H_INVOKESTATIC, "java/lang/invoke/LambdaMetafactory", "metafactory",
            "(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;Ljava/lang/invoke/MethodType;"
            + "Ljava/lang/invoke/MethodType;Ljava/lang/invoke/MethodHandle;Ljava/lang/invoke/MethodType;)Ljava/lang/invoke/CallSite;", false);
    private static int tests;
    private static void check(boolean ok, String label) { if (!ok) throw new AssertionError(label); }
    private static MethodNode method(ClassNode n, String name) {
        return n.methods.stream().filter(m -> m.name.equals(name)).findFirst().orElseThrow();
    }
    private static InvokeDynamicInsnNode dynamic(ClassNode n) {
        for (var i : method(n, "<init>").instructions) if (i instanceof InvokeDynamicInsnNode d) return d;
        throw new AssertionError("fixture_dynamic_missing");
    }
    private static byte[] bytes(ClassNode n) { ClassWriter w = new ClassWriter(0); n.accept(w); return w.toByteArray(); }
    static ClassNode fixture() {
        ClassWriter w = new ClassWriter(0);
        w.visit(Opcodes.V21, Opcodes.ACC_PUBLIC, OWNER, null, "java/lang/Object", null);
        for (String field : new String[]{"before", "after", "hardware"})
            w.visitField(Opcodes.ACC_PUBLIC, field, "I", null, null).visitEnd();
        var m = w.visitMethod(Opcodes.ACC_PUBLIC, "<init>", "()V", null, null); m.visitCode();
        m.visitVarInsn(Opcodes.ALOAD, 0); m.visitMethodInsn(Opcodes.INVOKESPECIAL, "java/lang/Object", "<init>", "()V", false);
        m.visitVarInsn(Opcodes.ALOAD, 0); m.visitIntInsn(Opcodes.BIPUSH, 11); m.visitFieldInsn(Opcodes.PUTFIELD, OWNER, "before", "I");
        m.visitVarInsn(Opcodes.ALOAD, 0); m.visitLdcInsn("hardware"); m.visitVarInsn(Opcodes.ALOAD, 0);
        m.visitInvokeDynamicInsn("run", "(L"+OWNER+";)Ljava/lang/Runnable;", BSM, Type.getMethodType("()V"),
                new Handle(Opcodes.H_INVOKEVIRTUAL, OWNER, NAME, "()V", false), Type.getMethodType("()V"));
        m.visitMethodInsn(Opcodes.INVOKEVIRTUAL, OWNER, "ignoreErrors", "(Ljava/lang/String;Ljava/lang/Runnable;)V", false);
        m.visitVarInsn(Opcodes.ALOAD, 0); m.visitIntInsn(Opcodes.BIPUSH, 22); m.visitFieldInsn(Opcodes.PUTFIELD, OWNER, "after", "I");
        m.visitInsn(Opcodes.RETURN); m.visitMaxs(3, 1); m.visitEnd();
        m=w.visitMethod(Opcodes.ACC_PRIVATE|Opcodes.ACC_SYNTHETIC, NAME, "()V", null, null); m.visitCode();
        m.visitVarInsn(Opcodes.ALOAD, 0); m.visitTypeInsn(Opcodes.NEW, "oshi/SystemInfo"); m.visitInsn(Opcodes.DUP);
        m.visitMethodInsn(Opcodes.INVOKESPECIAL, "oshi/SystemInfo", "<init>", "()V", false);
        m.visitMethodInsn(Opcodes.INVOKEVIRTUAL, OWNER, "putHardware", "(Loshi/SystemInfo;)V", false);
        m.visitInsn(Opcodes.RETURN); m.visitMaxs(3, 1); m.visitEnd();
        m=w.visitMethod(Opcodes.ACC_PRIVATE, "putHardware", "(Loshi/SystemInfo;)V", null, null); m.visitCode();
        m.visitVarInsn(Opcodes.ALOAD, 0); m.visitInsn(Opcodes.ICONST_1); m.visitFieldInsn(Opcodes.PUTFIELD, OWNER, "hardware", "I");
        m.visitInsn(Opcodes.RETURN); m.visitMaxs(2, 2); m.visitEnd();
        m=w.visitMethod(Opcodes.ACC_PRIVATE, "ignoreErrors", "(Ljava/lang/String;Ljava/lang/Runnable;)V", null, null); m.visitCode();
        m.visitVarInsn(Opcodes.ALOAD, 2); m.visitMethodInsn(Opcodes.INVOKEINTERFACE, "java/lang/Runnable", "run", "()V", true);
        m.visitInsn(Opcodes.RETURN); m.visitMaxs(1, 3); m.visitEnd();
        w.visitEnd(); ClassNode result = new ClassNode(); new ClassReader(w.toByteArray()).accept(result, 0); return result;
    }
    private static byte[] stub() {
        ClassWriter w=new ClassWriter(0); w.visit(Opcodes.V21, Opcodes.ACC_PUBLIC, "oshi/SystemInfo", null, "java/lang/Object", null);
        w.visitField(Opcodes.ACC_PUBLIC|Opcodes.ACC_STATIC, "created", "I", null, null).visitEnd();
        var m=w.visitMethod(Opcodes.ACC_PUBLIC,"<init>","()V",null,null); m.visitCode();
        m.visitVarInsn(Opcodes.ALOAD,0);m.visitMethodInsn(Opcodes.INVOKESPECIAL,"java/lang/Object","<init>","()V",false);
        m.visitFieldInsn(Opcodes.GETSTATIC,"oshi/SystemInfo","created","I");m.visitInsn(Opcodes.ICONST_1);m.visitInsn(Opcodes.IADD);
        m.visitFieldInsn(Opcodes.PUTSTATIC,"oshi/SystemInfo","created","I");m.visitInsn(Opcodes.RETURN);m.visitMaxs(2,1);m.visitEnd();
        w.visitEnd();return w.toByteArray();
    }
    private static final class FixtureLoader extends ClassLoader {
        private final Map<String,byte[]> definitions;
        FixtureLoader(byte[] target) { definitions=Map.of("net.minecraft.SystemReport",target,"oshi.SystemInfo",stub()); }
        @Override protected Class<?> findClass(String name) throws ClassNotFoundException {
            byte[] data=definitions.get(name);if(data==null)throw new ClassNotFoundException("fixture class absent");
            return defineClass(name,data,0,data.length);
        }
    }
    private static void behavior(byte[] target, boolean transformed) throws Exception {
        FixtureLoader loader=new FixtureLoader(target);Class<?> type=loader.loadClass("net.minecraft.SystemReport");
        for(int i=0;i<2;i++) {
            Object report=type.getConstructor().newInstance();
            check(type.getField("before").getInt(report)==11 && type.getField("after").getInt(report)==22,"nonhardware_fields_retained");
            check(type.getField("hardware").getInt(report)==(transformed?0:1),"hardware_only_omitted");
        }
        check(loader.loadClass("oshi.SystemInfo").getField("created").getInt(null)==(transformed?0:2),"no_oshi_allocation_after_transform");tests++;
    }
    private static Map<String,byte[]> methodBytes(ClassNode node) {
        Map<String,byte[]> out=new HashMap<>();
        for(MethodNode m:node.methods) {
            ClassWriter w=new ClassWriter(0);w.visit(Opcodes.V21,Opcodes.ACC_PUBLIC,OWNER,null,"java/lang/Object",null);m.accept(w);w.visitEnd();
            out.put(m.name+m.desc,w.toByteArray());
        }return out;
    }
    private static void reject(String label, Consumer<ClassNode> mutation) {
        ClassNode node=fixture();mutation.accept(node);byte[] before=bytes(node);
        try {new HardwareInventorySkipLaunchPlugin().processClassWithFlags(ILaunchPluginService.Phase.AFTER,node,TYPE,"classloading");
            throw new AssertionError("expected_fixed_refusal");
        } catch(HardwareInventorySkipLaunchPlugin.Refused refused) {
            check(refused.getStackTrace().length==0 && refused.getCause()==null && refused.getMessage().startsWith("hardware diagnostic refused: "),"bounded_refusal");
            check(Arrays.equals(before,bytes(node)),"mismatch_no_partial_mutation");
        }tests++;
    }
    public static void main(String[] args) throws Exception {
        ClassNode node=fixture();Map<String,byte[]> originalMethods=methodBytes(node);
        byte[] original=bytes(node);behavior(original,false);
        var plugin=new HardwareInventorySkipLaunchPlugin();
        check(plugin.handlesClass(TYPE,false,"classloading").equals(java.util.EnumSet.of(ILaunchPluginService.Phase.AFTER)),"after_only");
        check(plugin.handlesClass(TYPE,true,"classloading").isEmpty() && plugin.handlesClass(Type.getObjectType("unrelated/Type"),false,"classloading").isEmpty(),"target_only");
        for (String reason : new String[]{"computing_frames", "other-plugin", ""}) {
            check(plugin.handlesClass(TYPE,false,reason).isEmpty(),"analysis_reason_not_selected");
            check(plugin.processClassWithFlags(ILaunchPluginService.Phase.AFTER,node,TYPE,reason)==0,"analysis_no_rewrite");
            check(Arrays.equals(original,bytes(node)),"analysis_no_mutation");tests++;
        }
        check(plugin.handlesClass(TYPE,false).isEmpty(),"unspecified_reason_not_selected");
        int flags=plugin.processClassWithFlags(ILaunchPluginService.Phase.AFTER,node,TYPE,"classloading");
        check(flags==ILaunchPluginService.ComputeFlags.SIMPLE_REWRITE,"simple_rewrite");
        for(var entry:methodBytes(node).entrySet()) if(!entry.getKey().equals(NAME+"()V"))
            check(Arrays.equals(originalMethods.get(entry.getKey()),entry.getValue()),"other_methods_exact");
        check(method(node,NAME).instructions.size()==1 && method(node,NAME).instructions.getFirst().getOpcode()==Opcodes.RETURN,"return_only");
        behavior(bytes(node),true);
        try {plugin.processClassWithFlags(ILaunchPluginService.Phase.AFTER,node,TYPE,"classloading");throw new AssertionError("repeat_expected_refusal");}
        catch(HardwareInventorySkipLaunchPlugin.Refused expected) {tests++;}
        ClassNode unrelated=fixture();byte[] before=bytes(unrelated);
        check(plugin.processClassWithFlags(ILaunchPluginService.Phase.BEFORE,unrelated,Type.getObjectType("unrelated/Type"),"classloading")==0,"unrelated_no_rewrite");
        check(Arrays.equals(before,bytes(unrelated)),"unrelated_unchanged");tests++;
        reject("version",n->n.version=Opcodes.V17);
        reject("method_count",n->n.methods.remove(method(n,NAME)));
        reject("duplicate",n->n.methods.add(new MethodNode(Opcodes.ACC_PRIVATE|Opcodes.ACC_SYNTHETIC,NAME,"()V",null,null)));
        reject("access",n->method(n,NAME).access=Opcodes.ACC_PUBLIC);
        reject("extra_opcode",n->method(n,NAME).instructions.insert(new InsnNode(Opcodes.NOP)));
        reject("allocation",n->((TypeInsnNode)method(n,NAME).instructions.get(1)).desc="other/SystemInfo");
        reject("invocation",n->((MethodInsnNode)method(n,NAME).instructions.get(4)).name="otherHardware");
        reject("max_stack",n->method(n,NAME).maxStack=4);
        reject("handler",n->{LabelNode l=new LabelNode();method(n,NAME).instructions.insert(l);method(n,NAME).tryCatchBlocks.add(new TryCatchBlockNode(l,l,l,"java/lang/Exception"));});
        reject("label",n->{for(var i:method(n,"<init>").instructions)if(i instanceof LdcInsnNode l)l.cst="not_hardware";});
        reject("wrapper",n->{for(var i:method(n,"<init>").instructions)if(i instanceof MethodInsnNode m&&m.name.equals("ignoreErrors"))m.name="notIgnoreErrors";});
        reject("bootstrap",n->dynamic(n).bsm=new Handle(Opcodes.H_INVOKESTATIC,"unknown/Factory","metafactory",BSM.getDesc(),false));
        reject("handle",n->dynamic(n).bsmArgs[1]=new Handle(Opcodes.H_INVOKESTATIC,OWNER,NAME,"()V",false));
        reject("bootstrap_arg",n->dynamic(n).bsmArgs[2]=Type.getMethodType("()I"));
        reject("extra_binding",n->{MethodNode extra=new MethodNode(Opcodes.ACC_PRIVATE,"extra","()V",null,null);extra.instructions.add(new VarInsnNode(Opcodes.ALOAD,0));var d=dynamic(n);extra.instructions.add(new InvokeDynamicInsnNode(d.name,d.desc,d.bsm,d.bsmArgs));extra.instructions.add(new InsnNode(Opcodes.POP));extra.instructions.add(new InsnNode(Opcodes.RETURN));extra.maxStack=1;extra.maxLocals=1;n.methods.add(extra);});
        ClassNode wrongPhase=fixture();before=bytes(wrongPhase);
        try {new HardwareInventorySkipLaunchPlugin().processClassWithFlags(ILaunchPluginService.Phase.BEFORE,wrongPhase,TYPE,"classloading");throw new AssertionError("phase_expected_refusal");}
        catch(HardwareInventorySkipLaunchPlugin.Refused expected) {check(Arrays.equals(before,bytes(wrongPhase)),"phase_unchanged");tests++;}
        System.out.println("PASS hardware_skip_fixture tests="+tests+" real_hardware=false real_game=false baseline_acceptance=false");
    }
}
