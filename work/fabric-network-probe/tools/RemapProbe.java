// SPDX-License-Identifier: MIT
package net.neoforged.art.internal;
import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.function.Consumer;
import java.util.jar.*;
import java.util.zip.*;
import net.neoforged.art.api.ClassProvider;
import net.neoforged.art.api.Renamer;
import net.neoforged.art.api.Transformer;
import net.neoforged.art.internal.EnhancedRemapper;
import net.neoforged.art.relocated.net.neoforged.srgutils.IMappingFile;
import net.neoforged.art.relocated.net.neoforged.srgutils.INamedMappingFile;
import net.neoforged.art.relocated.org.objectweb.asm.*;

/** No custom bytecode substitution. Uses the original pinned ART inheritance-aware remapper.
 * Reverse verification views the same real named dependency hierarchy through mapped metadata;
 * no game class is loaded, no dependency JAR is modified, and no fake game/API class is created.
 */
public final class RemapProbe {
    static int logs;
    static final Consumer<String> LOG = s -> {
        if (++logs > 16384 || s.length() > 4096) throw new IllegalStateException("remapper_log_bound");
        System.out.println("ART_DIAGNOSTIC " + s);
        // Failing closed on incomplete hierarchy, not suppressing missing inheritance.
        if (s.contains("Can't Find Class") || s.contains("Could not find") || s.contains("Missing class"))
            throw new IllegalStateException("remapper_missing_hierarchy");
    };
    static void require(boolean ok, String code) { if (!ok) throw new IllegalStateException(code); }
    static byte[] normalized(byte[] bytes) {
        var out = new ClassWriter(0);
        new ClassReader(bytes).accept(out, ClassReader.SKIP_DEBUG);
        return out.toByteArray();
    }
    static Map<String,byte[]> classes(Path jar) throws IOException {
        var result = new TreeMap<String,byte[]>();
        try (var z = new ZipFile(jar.toFile())) {
            var entries = z.entries();
            while(entries.hasMoreElements()) {
                var e=entries.nextElement();
                if (!e.getName().endsWith(".class")) continue;
                require(e.getSize()>0 && e.getSize()<=262144, "probe_class_bound");
                require(result.size()<32, "probe_class_count");
                require(result.put(e.getName(),z.getInputStream(e).readAllBytes())==null,"duplicate_class");
            }
        }
        return result;
    }
    /** This is metadata for real dependency classes, not invented class implementations. */
    static ClassProvider mapped(ClassProvider original, IMappingFile map) {
        var forward = new EnhancedRemapper(original,map,LOG);
        var reverse = map.reverse();
        return new ClassProvider() {
            public Optional<? extends IClassInfo> getClass(String name) {
                return original.getClass(reverse.remapClass(name)).map(c -> new IClassInfo() {
                    public int getAccess(){return c.getAccess();}
                    public String getName(){return map.remapClass(c.getName());}
                    public String getSuper(){return c.getSuper()==null?null:map.remapClass(c.getSuper());}
                    public Collection<String> getInterfaces(){return c.getInterfaces().stream().map(map::remapClass).toList();}
                    public Collection<? extends IFieldInfo> getFields(){return c.getFields().stream().map(f -> new IFieldInfo(){
                        public int getAccess(){return f.getAccess();}
                        public String getName(){return forward.mapFieldName(c.getName(),f.getName(),f.getDescriptor());}
                        public String getDescriptor(){return map.remapDescriptor(f.getDescriptor());}
                    }).toList();}
                    public Optional<? extends IFieldInfo> getField(String n){return getFields().stream().filter(f->f.getName().equals(n)).findFirst();}
                    public Collection<? extends IMethodInfo> getMethods(){return c.getMethods().stream().map(m -> new IMethodInfo(){
                        public int getAccess(){return m.getAccess();}
                        public String getName(){return forward.mapMethodName(c.getName(),m.getName(),m.getDescriptor());}
                        public String getDescriptor(){return map.remapDescriptor(m.getDescriptor());}
                    }).toList();}
                    public Optional<? extends IMethodInfo> getMethod(String n,String d){return getMethods().stream().filter(m->m.getName().equals(n)&&m.getDescriptor().equals(d)).findFirst();}
                });
            }
            public void close() {} // Borrowed parent-owned provider.
        };
    }
    public static void main(String[] args) throws Exception {
        require(args.length==5,"args");
        Path mapping=Path.of(args[0]), input=Path.of(args[1]), output=Path.of(args[2]), roundtrip=Path.of(args[3]);
        require(!Files.exists(output)&&!Files.exists(roundtrip),"output_exists");
        var libs=Files.readAllLines(Path.of(args[4]));
        require(!libs.isEmpty()&&libs.size()<=160,"library_count");
        var named = INamedMappingFile.load(mapping.toFile());
        require(named.getNames().equals(List.of("official","intermediary","mojang")),"mapping_namespaces");
        var map=named.getMap("mojang","intermediary");
        require(!map.remapClass("net/minecraft/client/Minecraft").equals("net/minecraft/client/Minecraft"),"mapping_direction");
        var paths=new ArrayList<Path>();paths.add(input);
        for(String lib:libs){Path p=Path.of(lib);require(Files.isRegularFile(p),"library_missing");paths.add(p);}
        try(var raw=ClassProvider.fromPaths(paths.toArray(Path[]::new));var jvm=ClassProvider.fromJvmClasspath()) {
            ClassProvider combined=new ClassProvider(){
                public Optional<? extends IClassInfo> getClass(String n){var c=raw.getClass(n);return c.isPresent()?c:jvm.getClass(n);}
                public void close(){}
            };
            try(var remap=Renamer.builder().threads(1).logger(LOG).debug(LOG).addClassProvider(combined)
                    .add(Transformer.renamerFactory(map,false)).build()) {remap.run(input.toFile(),output.toFile());}
            try(var remap=Renamer.builder().threads(1).logger(LOG).debug(LOG).addClassProvider(mapped(combined,map))
                    .add(Transformer.renamerFactory(map.reverse(),false)).build()) {remap.run(output.toFile(),roundtrip.toFile());}
        }
        var before=classes(input);var after=classes(roundtrip);var middle=classes(output);
        require(!before.isEmpty()&&before.keySet().equals(after.keySet())&&before.keySet().equals(middle.keySet()),"class_set_changed");
        int changed=0, indy=0;
        for(var e:before.entrySet()){
            require(Arrays.equals(normalized(e.getValue()),normalized(after.get(e.getKey()))),"class_roundtrip_"+e.getKey());
            if(!Arrays.equals(normalized(e.getValue()),normalized(middle.get(e.getKey()))))changed++;
            final int[] n={0};new ClassReader(e.getValue()).accept(new ClassVisitor(Opcodes.ASM9){
                public MethodVisitor visitMethod(int a,String b,String c,String d,String[] ex){return new MethodVisitor(Opcodes.ASM9){
                    public void visitInvokeDynamicInsn(String a,String b,Handle h,Object... v){n[0]++;}
                };}
            },ClassReader.SKIP_DEBUG|ClassReader.SKIP_FRAMES);indy+=n[0];
        }
        require(changed>=4&&indy>0,"nontrivial_mapping_not_exercised");
        System.out.println("ACTUAL_ART_PROBE_ROUNDTRIP classes="+before.size()+" mapped_classes="+changed+" invokedynamic="+indy+" PASS");
    }
}
