import java.util.*;
import java.util.zip.ZipFile;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import org.sinytra.adapter.env.ann.*;
import org.sinytra.adapter.env.ctx.*;
import org.sinytra.adapter.env.param.*;
import org.sinytra.adapter.env.util.*;
import org.sinytra.adapter.patch.*;
import org.sinytra.adapter.patch.config.*;
import org.sinytra.adapter.patch.config.key.MixinKeys;
import org.sinytra.adapter.patch.mixin.*;
import org.sinytra.adapter.patch.processor.*;
import org.sinytra.adapter.patch.resolver.*;
import org.sinytra.adapter.util.*;
import org.sinytra.adapter.util.provider.*;
import static org.sinytra.adapter.env.param.MethodParameters.ParamGroup.*;
public class PostprocessRegression {
 static int checks=0;
 static void eq(Object expected,Object actual,String label) {checks++;if(!Objects.equals(expected,actual))throw new AssertionError(label+": expected="+expected+" actual="+actual);}
 static MixinContext context(MethodNode m, ClassLookup lookup, MixinType kind) {
  ClassNode c=new ClassNode();c.name="fixture/Mixin";c.superName="java/lang/Object";c.methods.add(m);
  List<Type> targets=List.of(Type.getObjectType("net/minecraft/world/level/biome/Biome"));
  PatchEnvironment env=new PatchEnvironmentImpl(null,lookup,lookup,null,null,0,null);
  return new MixinContext(kind,PatchContext.create(c,targets,env),new ClassTarget(targets,null),c,m,null,null,kind.getFlags());
 }
 static TxResult redirect(ClassLookup lookup,String owner,String method,String desc,int count,Type receiver) {
  RedirectMixin kind=new RedirectMixin();MethodNode m=new MethodNode(Opcodes.ACC_PRIVATE,"handler","()V",null,null);
  MixinContext ctx=context(m,lookup,kind);
  MethodParameters p=MethodParameters.builder().putTypes(METHOD_PARAMS,List.of()).putTypes(CAPTURED_PARAMS,List.of()).putTypes(LOCALS,List.of()).build();
  MutableConfiguration clean=MutableConfiguration.create().setTargetMethod(new MethodQualifier(null,"freeze","()V")).setParameters(p);
  MutableConfiguration dirty=clean.childConfig().inheritParameters().setTargetMethod(clean.getTargetMethod()).setAtData(AtData.create("INVOKE",new MethodInsnNode(Opcodes.INVOKEINTERFACE,owner,method,desc,true)));
  TxResult r=kind.postProcess(ctx,clean,dirty,new Recipe(clean,dirty,new Resolvers(),new Processors(),ctx));
  if(r==TxResult.SUCCESS){eq(count,dirty.getParameters().getTypes(METHOD_PARAMS).size(),"redirect arity");eq(receiver,dirty.getParameters().getTypes(METHOD_PARAMS).getFirst(),"symbolic receiver preserved");}
  return r;
 }
 static ClassNode cls(String name,String sup,String... interfaces){ClassNode c=new ClassNode();c.name=name;c.superName=sup;c.interfaces=new ArrayList<>(List.of(interfaces));return c;}
 static void syntheticRedirects() {
  Map<String,ClassNode> nodes=new HashMap<>();ClassNode object=cls("java/lang/Object",null);nodes.put(object.name,object);
  ClassNode parent=cls("fixture/Parent","java/lang/Object");parent.access=Opcodes.ACC_INTERFACE;parent.methods.add(new MethodNode(Opcodes.ACC_PUBLIC|Opcodes.ACC_ABSTRACT,"f","(I)Ljava/lang/Object;",null,null));nodes.put(parent.name,parent);
  ClassNode child=cls("fixture/Child","java/lang/Object",parent.name);child.access=Opcodes.ACC_INTERFACE;nodes.put(child.name,child);
  ClassLookup lookup=n->Optional.ofNullable(nodes.get(n));
  eq(TxResult.SUCCESS,redirect(lookup,child.name,"f","(I)Ljava/lang/Object;",2,Type.getObjectType(child.name)),"inherited interface resolved");
  parent.methods.getFirst().access=Opcodes.ACC_PUBLIC|Opcodes.ACC_STATIC;
  eq(TxResult.FAIL,redirect(lookup,child.name,"f","(I)Ljava/lang/Object;",2,null),"inherited static rejected");
  parent.methods.getFirst().access=Opcodes.ACC_PRIVATE;
  eq(TxResult.FAIL,redirect(lookup,child.name,"f","(I)Ljava/lang/Object;",2,null),"inherited private rejected");
  parent.methods.getFirst().access=Opcodes.ACC_PUBLIC;child.interfaces.clear();child.superName=parent.name;
  eq(TxResult.SUCCESS,redirect(lookup,child.name,"f","(I)Ljava/lang/Object;",2,Type.getObjectType(child.name)),"inherited superclass receiver preserved");
  eq(TxResult.FAIL,redirect(lookup,child.name,"missing","()V",0,null),"missing invocation rejected");
 }
 static void callback(boolean stat,boolean used,boolean cancellable,boolean targetVoid) {
  ClassLookup lookup=n->Optional.empty();InjectMixin kind=new InjectMixin();
  MethodNode m=new MethodNode(stat?Opcodes.ACC_STATIC:0,"handler","(JLorg/spongepowered/asm/mixin/injection/callback/CallbackInfoReturnable;)V",null,null);
  int slot=stat?2:3;if(used){m.instructions.add(new VarInsnNode(Opcodes.ALOAD,slot));m.instructions.add(new InsnNode(Opcodes.POP));}m.instructions.add(new InsnNode(Opcodes.RETURN));
  MixinContext ctx=context(m,lookup,kind);
  var annotation=org.sinytra.adapter.env.param.Annotation.builder("Lfixture/Keep;").visible(false).build();
  MethodParameters p=MethodParameters.builder().putTypes(METHOD_PARAMS,List.of(Type.LONG_TYPE)).put(CI_CIR,List.of(new Parameter(TypeConstants.CIR_TYPE,List.of(annotation)))).putTypes(LOCALS,List.of()).build();
  MutableConfiguration clean=MutableConfiguration.create().setTargetMethod(new MethodQualifier(null,"oldTarget","(J)Z")).setParameters(p).setProperty(MixinKeys.CANCELLABLE,cancellable);
  MutableConfiguration dirty=clean.childConfig().setTargetMethod(new MethodQualifier(null,"newTarget",targetVoid?"(J)V":"(J)Z"));
  eq(TxResult.SUCCESS,kind.postProcess(ctx,clean,dirty,new Recipe(clean,dirty,new Resolvers(),new Processors(),ctx)),"inject postprocess");
  eq(!used&&!cancellable&&targetVoid?TypeConstants.CI_TYPE:TypeConstants.CIR_TYPE,dirty.getParameters().getTypes(CI_CIR).getFirst(),"callback safety gate");
  eq(List.of(annotation),dirty.getParameters().get(CI_CIR).getFirst().annotations(),"callback annotations retained");
  eq(TypeConstants.CIR_TYPE,clean.getParameters().getTypes(CI_CIR).getFirst(),"clean configuration unmodified");
 }
 public static void main(String[] args)throws Exception {
  try(ZipFile zip=new ZipFile(args[0])) {
   ClassLookup lookup=new ZipClassLookup(zip);
   eq(TxResult.SUCCESS,redirect(lookup,"net/minecraft/world/level/LevelReader","getFluidState","(Lnet/minecraft/core/BlockPos;)Lnet/minecraft/world/level/material/FluidState;",2,Type.getObjectType("net/minecraft/world/level/LevelReader")),"real NeoForge LevelReader inherited interface");
   eq(TxResult.SUCCESS,redirect(lookup,"net/minecraft/world/level/block/state/BlockState","getBlock","()Lnet/minecraft/world/level/block/Block;",1,Type.getObjectType("net/minecraft/world/level/block/state/BlockState")),"real NeoForge BlockState superclass");
  }
  syntheticRedirects();
  for(boolean stat:List.of(false,true))for(boolean used:List.of(false,true))for(boolean cancel:List.of(false,true))for(boolean voidReturn:List.of(false,true))callback(stat,used,cancel,voidReturn);
  System.out.println("PASS: postprocess regression checks="+checks+" (real host hierarchy, interface/class receiver identity, static/private/missing rejection, 16 callback safety combinations)");
 }
}
