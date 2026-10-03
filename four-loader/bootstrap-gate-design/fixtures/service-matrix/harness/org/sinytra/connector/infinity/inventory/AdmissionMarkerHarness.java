package org.sinytra.connector.infinity.inventory;

import cpw.mods.modlauncher.api.*;
import net.neoforged.fml.loading.ModDirTransformerDiscoverer;
import net.neoforged.jarjar.selection.JarSelector;
import net.neoforged.neoforgespi.earlywindow.*;
import net.neoforged.neoforgespi.locating.*;
import java.io.*;
import java.net.*;
import java.nio.file.*;
import java.util.*;
import java.util.zip.*;

/** Test-only package access. Exercises real discovery edges; does not claim a complete ModLauncher layer launch. */
public final class AdmissionMarkerHarness {
    public static void main(String[] args) throws Exception {
        Path root = Path.of(args[0]).toRealPath(); String test = args[1];
        Path game = root.resolve("game"), markers = root.resolve("markers");
        System.setProperty("unified.gate.fixture.markers", markers.toString());
        List<BootstrapInstallation.Artifact> artifacts = new ArrayList<>();
        artifacts.add(new BootstrapInstallation.Artifact("owner.jar", "SELF", List.of(), "BOOT_OWNER"));
        if (test.equals("trusted")) artifacts.add(artifact(root, "game/mods/provider.jar", "connector"));
        if (test.equals("copied")) artifacts.add(artifact(root, "trusted/provider.jar", "connector"));
        if (test.equals("nested")) artifacts.add(artifact(root, "builtin.jar", "fabric_api"));
        var policy = new BootstrapInstallation.Policy(1,true,game.toString(),root.toString(),"neoforgeclient",
            "test-only",Map.of(),Map.of(),artifacts,List.of(),List.of(),"isolated-test");
        Map<Path,String> originals = new LinkedHashMap<>();
        try (var paths = Files.walk(root)) { for (Path path : paths.filter(p -> p.toString().endsWith(".jar")).toList()) originals.put(path,BootstrapInstallation.sha256(path)); }
        AdmissionSession session = AdmissionSession.initialize(policy);
        List<NamedPath> candidates = new ModDirTransformerDiscoverer().candidates(game);
        int constructed = 0;
        if (test.equals("nested")) {
            Path parent=game.resolve("mods/parent.jar"), builtin=root.resolve("builtin.jar");
            check(session.permits(List.of(parent,builtin)),"ordinary parent and real pinned provider must remain admitted");
            check(session.nestedArchive(parent,"nested/api.jar").isEmpty(),"excluded nested child must not be exposed");
            int[] deniedEdges={0};
            List<Path> selected=JarSelector.detectAndSelect(List.of(parent,builtin), AdmissionMarkerHarness::resource,
                (file,entry)-> { Optional<Path> child=session.nestedArchive(file,entry.toString()); if(child.isEmpty())deniedEdges[0]++;return child; },
                Path::toString, failures->new IllegalStateException("Real JarJar constraints failed: "+failures));
            check(selected.isEmpty() && deniedEdges[0]>=2,"both recursive and selected JarJar callbacks must reject child");
            try (URLClassLoader loader=new URLClassLoader(new URL[]{parent.toUri().toURL(),builtin.toUri().toURL()},ClassLoader.getPlatformClassLoader())) {
                Object result=loader.loadClass("fixture.content.ContentProbe").getMethod("run").invoke(null);
                check("real-managed-api".equals(result),"retained content must invoke actual managed API implementation");
            }
            check(candidates.isEmpty(),"ordinary parent cannot expose nested service providers");
        } else {
            URL[] urls=candidates.stream().flatMap(candidate->Arrays.stream(candidate.paths())).map(path->{try{return path.toUri().toURL();}catch(MalformedURLException e){throw new IllegalStateException(e);}}).toArray(URL[]::new);
            try (URLClassLoader loader=new URLClassLoader(urls,AdmissionMarkerHarness.class.getClassLoader()) {
                public Enumeration<URL> getResources(String name) throws IOException { return name.startsWith("META-INF/services/") ? findResources(name) : super.getResources(name); }
            }) {
                for (GraphicsBootstrapper value:ServiceLoader.load(GraphicsBootstrapper.class,loader)) {value.bootstrap(new String[0]);constructed++;}
                for (ITransformationService value:ServiceLoader.load(ITransformationService.class,loader)) {value.initialize(null);constructed++;}
                for (ImmediateWindowProvider value:ServiceLoader.load(ImmediateWindowProvider.class,loader)) {value.initialize(new String[0]);constructed++;}
                for (IModFileCandidateLocator value:ServiceLoader.load(IModFileCandidateLocator.class,loader)) {value.findCandidates(null,null);constructed++;}
                for (IModFileReader value:ServiceLoader.load(IModFileReader.class,loader)) {value.read(null,null);constructed++;}
                for (IDependencyLocator value:ServiceLoader.load(IDependencyLocator.class,loader)) {value.scanMods(List.of(),null);constructed++;}
            }
            boolean positive=test.equals("trusted")||test.equals("ordinary");
            check(constructed==(positive?6:0),"all six provider categories must agree with frozen admission");
            if(test.equals("copied"))check(candidates.isEmpty(),"byte-identical external copy must not inherit trusted origin");
            if(test.equals("reentry")) {
                Path denied=game.resolve("mods/provider.jar");
                check(!session.permits(List.of(denied)),"denied path reentry");
                try{session.bindRuntimeObject(new Object(),List.of(denied));throw new AssertionError("denied object reentry");}catch(IllegalStateException expected){}
                try{session.requireKnown(root.resolve("unknown.jar"));throw new AssertionError("unknown origin allowed");}catch(UncheckedIOException|IllegalStateException expected){}
            }
        }
        long markerCount;try(var paths=Files.list(markers)){markerCount=paths.count();}
        check(markerCount==(constructed==6?18:0),"each positive provider needs static, constructor and entry markers; negatives need zero");
        for(var entry:originals.entrySet())check(BootstrapInstallation.sha256(entry.getKey()).equals(entry.getValue()),"original input hash changed");
        check(AdmissionSession.class.getClassLoader()==TrustedPayloads.class.getClassLoader(),"single actual model classloader");
        System.out.println("PASS case="+test+" serviceCandidates="+candidates.size()+" constructed="+constructed+" markers="+markerCount+" originalsUnchanged="+originals.size()+" scope=discovery-edges-not-full-layer-launch");
    }
    private static BootstrapInstallation.Artifact artifact(Path root,String relative,String id)throws IOException{return new BootstrapInstallation.Artifact(relative,BootstrapInstallation.sha256(root.resolve(relative)),List.of(id),"MANAGED_ROOT");}
    private static Optional<InputStream> resource(Path file,Path entry){
        try{ZipFile zip=new ZipFile(file.toFile());ZipEntry resource=zip.getEntry(entry.toString());if(resource==null){zip.close();return Optional.empty();}
            return Optional.of(new FilterInputStream(zip.getInputStream(resource)){public void close()throws IOException{try{super.close();}finally{zip.close();}}});
        }catch(IOException e){throw new UncheckedIOException(e);}
    }
    private static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
}
