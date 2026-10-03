package org.sinytra.connector.quilt;

import java.nio.file.Path;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.lang.reflect.Proxy;
import org.quiltmc.loader.api.*;
import org.quiltmc.loader.api.entrypoint.*;
import org.quiltmc.loader.api.minecraft.MinecraftQuiltLoader;
import net.fabricmc.loader.impl.FabricLoaderImpl;
import net.fabricmc.loader.impl.metadata.ModMetadataParser;
import net.fabricmc.loader.impl.metadata.VersionOverrides;
import net.fabricmc.loader.impl.metadata.DependencyOverrides;

public final class QuiltApiTest {
    private static int assertions;
    private static void check(boolean value, String why) { assertions++; if (!value) throw new AssertionError(why); }
    private static void rejects(Class<? extends Throwable> type, Runnable action, String why) {
        try { action.run(); throw new AssertionError("Did not reject: " + why); } catch (Throwable t) { if (!type.isInstance(t)) throw new AssertionError(why,t); assertions++; }
    }
    private static net.fabricmc.loader.api.entrypoint.EntrypointContainer<Runnable> entry(net.fabricmc.loader.api.ModContainer provider, String definition, Runnable callback) {
        return new net.fabricmc.loader.api.entrypoint.EntrypointContainer<>() {
            public Runnable getEntrypoint() { return callback; }
            public net.fabricmc.loader.api.ModContainer getProvider() { return provider; }
            public String getDefinition() { return definition; }
        };
    }
    public static void main(String[] args) throws Exception {
        var metadata = ModMetadataParser.parseMetadata(new java.io.ByteArrayInputStream("""
            {"schemaVersion":1,"id":"native_probe","version":"1.2.3","custom":{
              "infinity:quilt_source":"/original/mods/native-probe.jar",
              "infinity:quilt_metadata":{"schema_version":1,"quilt_loader":{
                "id":"native-probe","group":"dev.fixture","version":"1.2.3+native",
                "metadata":{"name":"Native Probe","description":"original description",
                  "license":["MIT",{"id":"custom","name":"Custom License","url":"https://example.test/license","description":"custom terms"}],
                  "contributors":{"Alice":["Owner","Developer"],"Bob":"Tester"},
                  "contact":{"homepage":"https://example.test"},"icon":{"16":"small.png","64":"large.png"}},
                "depends":["java",{"id":"minecraft","versions":{"any":["=1.21.1","=1.21"]},"reason":"game"},
                  {"id":"quilt_loader","versions":">=0.25.0"}],
                "breaks":[{"id":"bad_mod","versions":"<2.0"}]},
                "custom_root":{"yes":true,"number":4,"empty":null},"array":["x",2]}}}
            """.getBytes(java.nio.charset.StandardCharsets.UTF_8)), "api-fixture", List.of(), new VersionOverrides(), new DependencyOverrides(Path.of("/nonexistent/api-test")), false);
        var host = (net.fabricmc.loader.api.ModContainer) Proxy.newProxyInstance(QuiltApiTest.class.getClassLoader(), new Class[]{net.fabricmc.loader.api.ModContainer.class}, (p,m,a) -> switch(m.getName()) {
            case "getMetadata" -> metadata;
            case "getRootPath", "getRoot" -> Path.of("/runtime/transformed/native_probe");
            case "getRootPaths" -> List.of(Path.of("/runtime/transformed/native_probe"));
            case "getContainingMod" -> Optional.empty();
            case "getContainedMods" -> List.of();
            case "hashCode" -> System.identityHashCode(p);
            case "equals" -> p == a[0];
            default -> throw new UnsupportedOperationException(m.getName());
        });
        FabricLoaderImpl.INSTANCE.mods.add(host);
        var view = QuiltBridge.wrap(host);
        check(QuiltBridge.wrap(host) == view, "stable container view identity");
        var m = view.metadata();
        check(m.id().equals("native-probe"), "raw id preserved over normalized host id");
        check(m.group().equals("dev.fixture"), "group preserved");
        check(m.version().raw().equals("1.2.3+native"), "native raw version preserved");
        check(m.name().equals("Native Probe") && m.description().equals("original description"), "display metadata");
        check(ModLicense.fromIdentifier("Apache-2.0").name().equals("Apache License 2.0"),"pinned Apache license lookup");
        check(ModLicense.fromIdentifier("MIT").url().equals("https://spdx.org/licenses/MIT.html"),"probe MIT license lookup");
        check(ModLicense.fromIdentifier("unknown-fixture-license")==null && ModLicense.fromIdentifierOrDefault("unknown-fixture-license").id().equals("unknown-fixture-license"),"unknown license fallback contract");
        check(m.licenses().size()==2 && m.licenses().stream().anyMatch(l->l.url().equals("https://example.test/license")), "full licenses");
        check(m.contributors().stream().filter(c->c.name().equals("Alice")).findFirst().orElseThrow().roles().size()==2, "multiple contributor roles");
        check(m.getContactInfo("homepage").equals("https://example.test"), "contact");
        check(m.icon(17).equals("large.png") && m.icon(200).equals("large.png") && m.icon(1).equals("small.png"), "icon size selection");
        check(m.containsValue("quilt_loader") && m.value("custom_root").asObject().get("yes").asBoolean(), "complete root values");
        rejects(UnsupportedOperationException.class,()->m.values().put("bad",m.value("quilt_loader")),"immutable root");
        rejects(UnsupportedOperationException.class,()->m.value("array").asArray().add(m.value("quilt_loader")),"immutable array");
        rejects(ClassCastException.class,()->m.value("custom_root").asString(),"wrong value coercion");
        check(view.getSourceType()==ModContainer.BasicSourceType.NORMAL_QUILT,"native source classification");
        check(view.getSourcePaths().equals(List.of(List.of(Path.of("/original/mods/native-probe.jar")))),"original source independent of transformed root");
        check(view.rootPath().equals(Path.of("/runtime/transformed/native_probe")),"root retains host resource view");
        check(view.getPath("assets/probe.txt").equals(view.rootPath().resolve("assets/probe.txt")),"resource resolution");
        check(view.getClassLoader()==QuiltApiTest.class.getClassLoader(),"single host classloader");
        var nestedMetadata = ModMetadataParser.parseMetadata(new java.io.ByteArrayInputStream("""
            {"schemaVersion":1,"id":"quilt_base","version":"10.0.0-alpha.5+1.21.1","custom":{
              "infinity:quilt_source":"/cache/verified/qsl-base-original.jar",
              "infinity:quilt_source_chain":["/installed/mods/host-bundle.jar","META-INF/jarjar/qsl-base-original.jar"],
              "infinity:quilt_metadata":{"schema_version":1,"quilt_loader":{
                "id":"quilt_base","group":"org.quiltmc.qsl.core","version":"10.0.0-alpha.5+1.21.1"}}}}
            """.getBytes(java.nio.charset.StandardCharsets.UTF_8)), "nested-api-fixture", List.of(), new VersionOverrides(), new DependencyOverrides(Path.of("/nonexistent/api-test")), false);
        var nestedHost = (net.fabricmc.loader.api.ModContainer) Proxy.newProxyInstance(QuiltApiTest.class.getClassLoader(), new Class[]{net.fabricmc.loader.api.ModContainer.class}, (p,method,a) -> {
            if (method.getName().equals("getMetadata")) return nestedMetadata;
            return method.invoke(host,a);
        });
        var nestedView = QuiltBridge.wrap(nestedHost);
        var expectedChain = List.of(List.of(Path.of("/installed/mods/host-bundle.jar"),Path.of("META-INF/jarjar/qsl-base-original.jar")));
        check(nestedView.getSourcePaths().equals(expectedChain),"embedded source chain takes precedence over extracted transformer input");
        check(nestedView.host().getMetadata().getCustomValue(QuiltBridge.SOURCE_KEY).getAsString().equals("/cache/verified/qsl-base-original.jar"),"verified transformer-input carrier remains unchanged");
        check(nestedView.rootPath().equals(view.rootPath()),"nested original chain does not replace admitted runtime root");
        check(!nestedView.getSourcePaths().getFirst().get(1).isAbsolute(),"nested relative archive path preserved");
        rejects(UnsupportedOperationException.class,()->nestedView.getSourcePaths().clear(),"source-chain outer list immutable");
        rejects(UnsupportedOperationException.class,()->nestedView.getSourcePaths().getFirst().clear(),"source-chain path list immutable");
        check(QuiltLoader.getModContainer("native-probe").orElseThrow()==view,"native id lookup");
        check(QuiltLoader.getModContainer("native_probe").orElseThrow()==view,"host id lookup");
        check(QuiltLoader.isModLoaded("quilt_loader"),"builtin API provider");
        check(QuiltLoader.getAllMods().stream().filter(c->c.metadata().id().equals("quilt_loader")).count()==1,"exactly one builtin provider view");
        check(QuiltLoader.getModContainer("quilt_loader").orElseThrow().getSourceType()==ModContainer.BasicSourceType.BUILTIN,"builtin classification");
        check(QuiltLoader.getGameDir().equals(FabricLoaderImpl.INSTANCE.getGameDir()),"host game directory");
        check(QuiltLoader.getConfigDir().equals(FabricLoaderImpl.INSTANCE.getConfigDir()),"host config directory");
        check(MinecraftQuiltLoader.getEnvironmentType()==net.fabricmc.api.EnvType.SERVER,"host environment");
        check(QuiltLoader.getMappingResolver().getCurrentRuntimeNamespace().equals("named"),"actual host mapping namespace");
        check(QuiltLoader.getMappingResolver().mapMethodName("intermediary","Owner","run","()V").equals("method_run"),"mapping owner delegated");
        check(m.depends().size()==3 && m.breaks().size()==1,"exact dependency counts");
        var minecraft = m.depends().stream().map(d->(ModDependency.Only)d).filter(d->d.id().id().equals("minecraft")).findFirst().orElseThrow();
        check(minecraft.matches(Version.of("1.21.1")) && minecraft.matches(Version.of("1.21")) && !minecraft.matches(Version.of("1.22")),"version alternatives stay OR");
        check(Version.of("1.0.0-alpha.2").compareTo(Version.of("1.0.0-alpha.10"))<0,"numeric prerelease ordering");
        check(Version.of("1.0.0+foo").compareTo(Version.of("1.0.0+bar"))==0,"build metadata ignored in compare");
        check(Version.Semantic.of("1.0-").isPreReleasePresent(),"empty but present prerelease");
        check(!Version.of("release-name").isSemantic(),"raw version identity supported");
        rejects(UnsupportedOperationException.class,()->Version.of("raw-a").compareTo(Version.of("raw-b")),"unsupported raw version ordering explicit");
        check(VersionRange.ofInterval(Version.of("1"),true,Version.of("3"),false).combineMatchingBoth(VersionRange.ofInterval(Version.of("2"),true,null,false)).isSatisfiedBy(Version.of("2.1")),"version interval intersection");
        var overlapping = VersionRange.ofIntervals(List.of(VersionInterval.of(Version.of("1"),true,Version.of("4"),false),VersionInterval.of(Version.of("2"),true,Version.of("6"),false)));
        check(overlapping.size()==1 && overlapping.isSatisfiedBy(Version.of("5")),"overlapping union must never narrow");
        var touching = VersionRange.ofIntervals(List.of(VersionInterval.of(Version.of("1"),true,Version.of("2"),false),VersionInterval.of(Version.of("2"),true,Version.of("3"),false)));
        check(touching.size()==1,"touching inclusive endpoint coalesces");
        rejects(UnsupportedOperationException.class,()->VersionRange.ANY.clear(),"shared ANY immutable");
        check(VersionRange.ANY.isSatisfiedBy(Version.of("99")),"ANY retained after mutation attempt");
        var converted = VersionRange.ofInterval(Version.of("1"),true,null,false).convertToConstraints().iterator().next();
        check(converted.type()==VersionConstraint.Type.GREATER_THAN_OR_EQUAL,"legacy constraints preserve lower inclusive bound");
        QuiltBridge.recordResolvedOrder(List.of("native-probe", "quilt_base"));
        rejects(IllegalArgumentException.class, () -> QuiltBridge.recordResolvedOrder(List.of("native-probe", "native-probe")), "duplicate canonical provider order rejected");
        List<String> callbackOrder = new ArrayList<>();
        var firstConsumer = entry(host, "consumer-first", () -> callbackOrder.add("consumer-first"));
        var secondConsumer = entry(host, "consumer-second", () -> callbackOrder.add("consumer-second"));
        var bootstrap = entry(nestedHost, "base-bootstrap", () -> callbackOrder.add("base-bootstrap"));
        FabricLoaderImpl.INSTANCE.entries.put("init", List.of(firstConsumer, bootstrap, secondConsumer));
        check(QuiltLoader.getEntrypointContainers("init", Runnable.class).getFirst().getDefinition().equals("base-bootstrap"), "explicit pinned base bootstrap precedes consumers");
        check(callbackOrder.isEmpty(), "ordering native views does not instantiate or invoke callbacks");
        QuiltBridge.invokeContainer("init", Runnable.class, e -> e.getEntrypoint().run());
        check(callbackOrder.equals(List.of("base-bootstrap", "consumer-first", "consumer-second")), "base initialization first with stable per-provider order");
        FabricLoaderImpl.INSTANCE.entries.put("ordered-event", List.of(bootstrap, secondConsumer, firstConsumer));
        check(QuiltLoader.getEntrypointContainers("ordered-event", Runnable.class).stream().map(EntrypointContainer::getDefinition).toList().equals(List.of("consumer-second", "consumer-first", "base-bootstrap")), "other keys preserve canonical selected order and same-provider array order");
        AtomicInteger calls = new AtomicInteger(), creations = new AtomicInteger();
        Runnable callback = calls::incrementAndGet;
        FabricLoaderImpl.INSTANCE.entries.put("init",List.of(new net.fabricmc.loader.api.entrypoint.EntrypointContainer<Runnable>() {
            public Runnable getEntrypoint(){creations.incrementAndGet();return callback;}
            public net.fabricmc.loader.api.ModContainer getProvider(){return host;}
            public String getDefinition(){return "fixture::callback";}
        }));
        check(QuiltLoader.getEntrypointContainers("init",Runnable.class).getFirst().getDefinition().equals("fixture::callback"),"entrypoint definition");
        check(creations.get()==0,"container retrieval remains lazy");
        QuiltBridge.invokeOnce("init",Runnable.class,(entry,provider)->{check(provider==view,"provider view");entry.run();});
        QuiltBridge.invokeOnce("init",Runnable.class,(entry,provider)->entry.run());
        check(calls.get()==1 && creations.get()==1,"single host store + once-only stage");
        rejects(IllegalStateException.class, () -> QuiltBridge.recordResolvedOrder(List.of("quilt_base", "native-probe")), "resolved order cannot change after dispatch");
        ClassLoader previousContext = Thread.currentThread().getContextClassLoader();
        try {
            Thread.currentThread().setContextClassLoader(null);
            check(view.getClassLoader()==previousContext,"container classloader stays pinned when caller context changes");
        } finally { Thread.currentThread().setContextClassLoader(previousContext); }
        FabricLoaderImpl.INSTANCE.entries.put("events",FabricLoaderImpl.INSTANCE.entries.get("init"));
        check(QuiltLoader.getEntrypoints("events",Runnable.class).getFirst()==callback,"QSL automatic events key delegates host store");
        var broken = new net.fabricmc.loader.api.entrypoint.EntrypointContainer<Runnable>() {
            public Runnable getEntrypoint(){return ()->{throw new IllegalArgumentException("fixture failure");};}
            public net.fabricmc.loader.api.ModContainer getProvider(){return host;}
        };
        FabricLoaderImpl.INSTANCE.entries.put("broken",List.of(broken,broken));
        try { EntrypointUtil.invoke("broken",Runnable.class,Runnable::run); throw new AssertionError("missing entrypoint failure"); }
        catch(EntrypointException e) { check(e.getKey().equals("broken") && e.getSuppressed().length==1 && e.getMessage().contains("native-probe") && e.getMessage().contains("/original/mods/"),"aggregate preserves stage/provider/source"); }
        FabricLoaderImpl.INSTANCE.entries.put("broken-once",List.of(broken));
        rejects(EntrypointException.class,()->QuiltBridge.invokeOnce("broken-once",Runnable.class,(e,p)->e.run()),"stage failure retained");
        int reads=FabricLoaderImpl.INSTANCE.reads;
        rejects(EntrypointException.class,()->QuiltBridge.invokeOnce("broken-once",Runnable.class,(e,p)->e.run()),"failed stage not silently skipped");
        check(reads==FabricLoaderImpl.INSTANCE.reads,"failed stage never rereads or replays entrypoints");
        System.out.println("PASS: " + assertions + " Quilt API/host-view assertions; no game or third-party mod execution");
    }
}
