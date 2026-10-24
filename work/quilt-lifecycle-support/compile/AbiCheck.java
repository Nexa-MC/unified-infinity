// SPDX-License-Identifier: MIT
import java.nio.file.*;
import java.util.*;
import java.util.zip.*;
import net.neoforged.art.api.ClassProvider;
import net.neoforged.art.relocated.org.objectweb.asm.*;

/** Reads real class files only: no class initialization, runtime launch, or stub generation. */
public final class AbiCheck {
    static ClassProvider provider;
    static final Set<String> checked = new TreeSet<>();
    static boolean relevant(String owner) {
        return owner.startsWith("org/quiltmc/") || owner.startsWith("net/minecraft/") || owner.startsWith("org/spongepowered/") || owner.startsWith("dev/infinity/quiltprobe/");
    }
    static boolean resolve(String owner, String name, String desc, boolean method, Set<String> seen) {
        if (!seen.add(owner)) return false;
        var info = provider.getClass(owner).orElseThrow(() -> new IllegalStateException("Missing real class " + owner));
        boolean found = method ? info.getMethod(name, desc).isPresent() : info.getFields().stream().anyMatch(f -> f.getName().equals(name) && f.getDescriptor().equals(desc));
        if (found) return true;
        if (name.equals("<init>")) return false;
        if (info.getSuper() != null && resolve(info.getSuper(), name, desc, method, seen)) return true;
        for (String parent : info.getInterfaces()) if (resolve(parent, name, desc, method, seen)) return true;
        return false;
    }
    static void check(String owner, String name, String desc, boolean method) {
        if (!relevant(owner)) return;
        if (!resolve(owner, name, desc, method, new HashSet<>())) throw new IllegalStateException("Unresolved ABI " + owner + "." + name + desc);
        checked.add((method ? "METHOD " : "FIELD ") + owner + "." + name + desc);
    }
    static void handle(Object value) {
        if (value instanceof Handle h) check(h.getOwner(), h.getName(), h.getDesc(), h.getTag() > Opcodes.H_PUTSTATIC);
    }
    public static void main(String[] args) throws Exception {
        var paths = new ArrayList<Path>(); paths.add(Path.of(args[0]));
        for (String line : Files.readAllLines(Path.of(args[1]))) paths.add(Path.of(line));
        try (var raw = ClassProvider.fromPaths(paths.toArray(Path[]::new)); var jvm = ClassProvider.fromJvmClasspath()) {
            provider = new ClassProvider() {
                public Optional<? extends IClassInfo> getClass(String n) { var c = raw.getClass(n); return c.isPresent() ? c : jvm.getClass(n); }
                public void close() {}
            };
            int classes = 0;
            try (var jar = new ZipFile(args[0])) {
                for (var entry : Collections.list(jar.entries())) {
                    if (!entry.getName().endsWith(".class")) continue;
                    classes++;
                    new ClassReader(jar.getInputStream(entry)).accept(new ClassVisitor(Opcodes.ASM9) {
                        public MethodVisitor visitMethod(int access, String name, String desc, String signature, String[] exceptions) {
                            return new MethodVisitor(Opcodes.ASM9) {
                                public void visitMethodInsn(int op, String owner, String name, String desc, boolean itf) { check(owner, name, desc, true); }
                                public void visitFieldInsn(int op, String owner, String name, String desc) { check(owner, name, desc, false); }
                                public void visitInvokeDynamicInsn(String name, String desc, Handle bootstrap, Object... values) { handle(bootstrap); for (Object value : values) handle(value); }
                                public void visitLdcInsn(Object value) { handle(value); }
                            };
                        }
                    }, ClassReader.SKIP_DEBUG | ClassReader.SKIP_FRAMES);
                }
            }
            check("org/quiltmc/loader/api/entrypoint/PreLaunchEntrypoint", "onPreLaunch", "(Lorg/quiltmc/loader/api/ModContainer;)V", true);
            check("org/quiltmc/qsl/base/api/entrypoint/ModInitializer", "onInitialize", "(Lorg/quiltmc/loader/api/ModContainer;)V", true);
            check("org/quiltmc/qsl/base/api/entrypoint/server/DedicatedServerModInitializer", "onInitializeServer", "(Lorg/quiltmc/loader/api/ModContainer;)V", true);
            check("org/quiltmc/qsl/base/api/entrypoint/client/ClientModInitializer", "onInitializeClient", "(Lorg/quiltmc/loader/api/ModContainer;)V", true);
            check("org/quiltmc/qsl/lifecycle/api/event/ServerLifecycleEvents$Ready", "readyServer", "(Lnet/minecraft/server/MinecraftServer;)V", true);
            check("net/minecraft/class_18", "method_75", "(Lnet/minecraft/class_2487;Lnet/minecraft/class_7225$class_7874;)Lnet/minecraft/class_2487;", true);
            check("net/minecraft/server/MinecraftServer", "method_3748", "(Ljava/util/function/BooleanSupplier;)V", true);
            for (String member : checked) System.out.println(member);
            System.out.println("ACTUAL_CLASSFILE_ABI_BINDING classes=" + classes + " members=" + checked.size() + " PASS");
        }
    }
}
