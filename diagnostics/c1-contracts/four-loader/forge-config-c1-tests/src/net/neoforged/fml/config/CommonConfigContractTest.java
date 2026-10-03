package net.neoforged.fml.config;

import com.electronwill.nightconfig.core.CommentedConfig;
import com.electronwill.nightconfig.core.file.FileWatcher;
import com.electronwill.nightconfig.toml.TomlParser;
import com.electronwill.nightconfig.toml.TomlWriter;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.atomic.*;
import net.neoforged.fml.ModContainer;
import net.neoforged.fml.event.config.ModConfigEvent;
import net.neoforged.neoforge.common.ModConfigSpec;
import org.sinytra.connector.forge.config.*;

/** Real NightConfig parsing and owner IO; only loader bootstrap/event sink/watch scheduling are fixtures. */
public final class CommonConfigContractTest {
    static int assertions;
    static Path root;
    static void check(boolean ok, String message) { assertions++; if (!ok) throw new AssertionError(message); }
    static void equal(Object a, Object b, String message) { check(Objects.equals(a,b), message+": "+a+" != "+b); }
    static Throwable fails(Class<? extends Throwable> type, Runnable action, String message) {
        try { action.run(); } catch (Throwable t) { check(type.isInstance(t),message+": "+t); return t; }
        throw new AssertionError(message+": expected "+type);
    }
    record Values(ForgeConfigSpec spec, ForgeConfigSpec.BooleanValue enabled, ForgeConfigSpec.IntValue limit,
                  ForgeConfigSpec.IntValue restart, ForgeConfigSpec.ConfigValue<String> label,
                  ForgeConfigSpec.ConfigValue<List<? extends String>> tags) {}
    static Values values() {
        var b=new ForgeConfigSpec.Builder(); b.comment("Probe section").translation("infinity.probe.config").push("probe");
        var enabled=b.comment("Enable probe").define("enabled",true);
        var limit=b.comment("Bounded probe value").defineInRange("limit",4,1,9);
        var restart=b.worldRestart().defineInRange("restartValue",2,0,9);
        var label=b.define("label","seed");
        var tags=b.defineListAllowEmpty("tags",List.of("safe"), x->x instanceof String);
        b.pop(); return new Values(b.build(),enabled,limit,restart,label,tags);
    }
    static CommentedConfig disk(Path file) throws Exception { return new TomlParser().parse(Files.newBufferedReader(file)); }
    static void write(Path file, CommentedConfig config) throws Exception { Files.writeString(file,new TomlWriter().writeToString(config)); }
    static void register(ConfigTracker tracker, ModContainer container, Values v, String name) {
        ForgeConfigSpecAdapter.register(tracker,container,ForgeModConfig.Type.COMMON,v.spec(),name);
    }
    static void fire(Path file) throws Exception {
        var failure=new AtomicReference<Throwable>();
        var sentinel=new ClassLoader(){};
        var t=new Thread(()->{
            Thread.currentThread().setContextClassLoader(sentinel);
            try { FileWatcher.defaultInstance().fire(file); check(Thread.currentThread().getContextClassLoader()==sentinel,"watch context restored"); }
            catch(Throwable e){failure.set(e);}
        },"c1-owner-watch-callback");
        t.start();t.join(5000); check(!t.isAlive(),"callback terminates");
        if(failure.get()!=null)throw new AssertionError("watch failure",failure.get());
    }
    static void lifecycle() throws Exception {
        var tracker=new ConfigTracker();var owner=new ModContainer("forge_lifecycle");var v=values();
        var path=root.resolve("config/lifecycle.toml"); var identity=new AtomicReference<ForgeModConfig>();
        owner.listener=e->{
            check(e instanceof ForgeModConfigEvent,"Forge event family only");
            var c=((ForgeModConfigEvent)e).getConfig();
            check(c.getSpec()==v.spec(),"original Forge spec identity");
            check(v.spec().isLoaded(),"loaded before event");
            equal(c.getType(),ForgeModConfig.Type.COMMON,"COMMON getter");
            equal(c.getModId(),"forge_lifecycle","mod ownership"); equal(c.getFileName(),"lifecycle.toml","filename");
            if(identity.get()==null)identity.set(c);else check(identity.get()==c,"stable facade identity");
            if(e instanceof ForgeModConfigEvent.Loading){ int count=owner.events.size();v.spec().save();equal(owner.events.size(),count,"save during Loading does not recurse"); }
            else equal(Thread.currentThread().getName(),"c1-owner-watch-callback","reload callback thread");
        };
        register(tracker,owner,v,"lifecycle.toml");
        ForgeConfigSpecAdapter.register(tracker,owner,ForgeModConfig.Type.COMMON,new ForgeConfigSpec.Builder().build(),"empty.toml");
        equal(tracker.fileMap.size(),1,"one native tracked config; empty skipped");
        tracker.loadConfigs(ModConfig.Type.COMMON,root.resolve("config"));
        equal(FileWatcher.defaultInstance().count(),1,"one owner watch"); check(!Files.exists(root.resolve("config/empty.toml")),"no empty file");
        equal(owner.events.size(),1,"single Loading");equal(v.limit().get(),4,"default int");equal(v.restart().get(),2,"default restart");
        check(Files.readString(path).contains("Bounded probe value"),"Forge comments persisted");
        var changed=disk(path);changed.set("probe.limit",8);changed.set("probe.restartValue",9);write(path,changed);fire(path);
        equal(owner.events.size(),2,"one event per callback");equal(v.limit().get(),8,"reload invalidates ordinary cache");equal(v.restart().get(),9,"reload invalidates worldRestart cache");
        changed=disk(path);changed.set("probe.limit",99);changed.remove("probe.enabled");changed.set("probe.unknown",true);changed.set("probe.tags",List.of("kept",5));write(path,changed);
        String before=Files.readString(path);fire(path);
        equal(v.limit().get(),9,"clamp");equal(v.enabled().get(),true,"restore missing");equal(v.tags().get(),List.of("kept"),"filter invalid list");
        check(!disk(path).contains("probe.unknown"),"remove unknown key");equal(Files.readString(root.resolve("config/lifecycle-1.toml.bak")),before,"reload backup preserves old bytes");
        equal(owner.events.size(),3,"correction causes no recursive event");
        v.enabled().set(false);v.limit().set(6);v.restart().set(7);v.label().set("saved");v.tags().set(List.of("kept","saved"));
        var saved=disk(path);equal(saved.get("probe.limit"),6,"set autosaves before explicit save");equal(saved.get("probe.restartValue"),7,"restart set autosaves");
        equal(v.restart().get(),7,"restart set updates cache"); equal(owner.events.size(),3,"no synthetic event during set");
        v.spec().save();v.limit().save();equal(owner.events.size(),3,"explicit save has no synchronous reload");
        tracker.unloadConfigs(ModConfig.Type.COMMON);equal(FileWatcher.defaultInstance().count(),0,"owner disposal detaches watcher");
        var fresh=new ConfigTracker();var freshOwner=new ModContainer("forge_lifecycle");var reopened=values();register(fresh,freshOwner,reopened,"lifecycle.toml");fresh.loadConfigs(ModConfig.Type.COMMON,root.resolve("config"));
        equal(reopened.label().get(),"saved","fresh spec reopen label");equal(reopened.restart().get(),7,"fresh spec reopen restart");equal(reopened.tags().get(),List.of("kept","saved"),"fresh spec reopen list");
        check(reopened.spec()!=v.spec(),"fresh spec identity");equal(freshOwner.events.size(),1,"fresh Loading");fresh.unloadConfigs(ModConfig.Type.COMMON);
    }
    static void creationAndErrors() throws Exception {
        for(boolean template:List.of(false,true)) {
            var tracker=new ConfigTracker();var owner=new ModContainer("creation_"+template);var v=values();var file="creation_"+template+".toml";
            var path=root.resolve("config/"+file);var seed=CommentedConfig.inMemory();v.spec().correct(seed);seed.set("probe.limit",99);
            var input=template?root.resolve("defaultconfigs/"+file):path;Files.createDirectories(input.getParent());write(input,seed);
            register(tracker,owner,v,file);tracker.loadConfigs(ModConfig.Type.COMMON,root.resolve("config"));
            equal(v.limit().get(),9,"invalid "+(template?"template":"existing file")+" corrected");
            equal(owner.events.size(),1,"no Reloading before initial Loading");check(!Files.exists(path.resolveSibling("creation_"+template+"-1.toml.bak")),"no initial correction backup");tracker.unloadConfigs(ModConfig.Type.COMMON);
        }
        var tracker=new ConfigTracker();var owner=new ModContainer("default_name");var v=values();register(tracker,owner,v,null);
        check(tracker.fileMap.containsKey("default_name-common.toml"),"default filename");
        fails(RuntimeException.class,()->register(tracker,new ModContainer("collision"),values(),"default_name-common.toml"),"filename collision rejected");equal(tracker.fileMap.size(),1,"collision doesn't add tracked config");
        var bad=root.resolve("config/default_name-common.toml");Files.writeString(bad,"invalid = [");String bytes=Files.readString(bad);
        var t=fails(RuntimeException.class,()->tracker.loadConfigs(ModConfig.Type.COMMON,root.resolve("config")),"malformed initial load fails");
        check(t.getMessage().contains("default_name-common.toml")&&t.getMessage().contains("COMMON")&&t.getMessage().contains("default_name")&&t.getCause()!=null,"error has file/type/mod/cause");
        equal(Files.readString(bad),bytes,"malformed initial bytes preserved");check(!v.spec().isLoaded(),"failed load not accepted");equal(owner.events.size(),0,"no success event after malformed load");
        Files.delete(bad);tracker.loadConfigs(ModConfig.Type.COMMON,root.resolve("config"));v.limit().get();Files.writeString(bad,bytes);
        fails(RuntimeException.class,()->FileWatcher.defaultInstance().fire(bad),"malformed reload fails");equal(Files.readString(bad),bytes,"malformed reload bytes preserved");equal(owner.events.size(),1,"no successful reload invented");equal(v.limit().get(),4,"old accepted state survives failed reload");tracker.unloadConfigs(ModConfig.Type.COMMON);
    }
    static void nativeControls() throws Exception {
        var tracker=new ConfigTracker();var owner=new ModContainer("native_control");var b=new ModConfigSpec.Builder();var ordinary=b.defineInRange("ordinary",1,0,9);var restart=b.worldRestart().defineInRange("restart",2,0,9);var spec=b.build();
        fails(IllegalStateException.class,ordinary::get,"native built-unloaded read remains strict");
        var forgeOwner=new ModContainer("forge_alongside_native");var forgeValues=values();
        register(tracker,forgeOwner,forgeValues,"alongside.toml");
        var config=tracker.registerConfig(ModConfig.Type.COMMON,spec,owner,"native.toml");tracker.loadConfigs(ModConfig.Type.COMMON,root.resolve("config"));var path=root.resolve("config/native.toml");
        equal(restart.get(),2,"native restart cached");var data=disk(path);data.set("ordinary",7);data.set("restart",8);write(path,data);fire(path);
        equal(ordinary.get(),7,"native ordinary invalidated");equal(restart.get(),2,"native restart cache preserved");
        int count=owner.events.size();config.getLoadedConfig().save();equal(owner.events.size(),count+1,"native save immediate Reloading preserved");
        check(owner.events.stream().allMatch(e->e instanceof ModConfigEvent),"native configs never receive Forge events");
        int forgeCount=forgeOwner.events.size();forgeValues.limit().set(5);forgeValues.spec().save();
        equal(forgeOwner.events.size(),forgeCount,"Forge save remains quiet alongside native owner");
        equal(owner.events.size(),count+1,"Forge mutation does not dispatch to native owner");
        check(forgeOwner.events.stream().allMatch(e->e instanceof ForgeModConfigEvent),"Forge event family scoped per registration");
        Files.writeString(path,"bad = [");fire(path);equal(ordinary.get(),1,"native malformed recovery retained");check(disk(path).contains("ordinary"),"native replacement file is valid");tracker.unloadConfigs(ModConfig.Type.COMMON);
    }
    static void pinnedOracleAndBoundaries() throws Exception {
        var b=new ForgeConfigSpec.Builder();var x=b.defineInRange("x",4,1,9);fails(NullPointerException.class,x::get,"pre-build NPE");var spec=b.build();equal(x.get(),4,"Forge production default before load");
        net.neoforged.fml.loading.FMLEnvironment.production=false;fails(IllegalStateException.class,x::get,"Forge dev fails before load");net.neoforged.fml.loading.FMLEnvironment.production=true;
        var officialBuilder=new net.minecraftforge.common.ForgeConfigSpec.Builder();var official=officialBuilder.comment("bounded").defineInRange("x",4,1,9);var officialSpec=officialBuilder.build();
        var candidateBuilder=new ForgeConfigSpec.Builder();var candidate=candidateBuilder.comment("bounded").defineInRange("x",4,1,9);var candidateSpec=candidateBuilder.build();
        for(Object invalid:List.of(99,-5,"bad",2)) {
            var left=CommentedConfig.inMemory();left.set("x",invalid);left.set("unknown",true);var right=CommentedConfig.inMemory();right.set("x",invalid);right.set("unknown",true);
            equal(candidateSpec.correct(left),officialSpec.correct(right),"official correction count "+invalid);equal(new TomlWriter().writeToString(left),new TomlWriter().writeToString(right),"official corrected values/comments "+invalid);
        }
        var valid=CommentedConfig.inMemory();candidateSpec.correct(valid);var adapter=new ForgeConfigSpecAdapter(candidateSpec);check(adapter.isCorrect(valid.unmodifiable()),"adapter accepts true immutable view");
        equal(ForgeConfigSpec.class.getMethod("correct",CommentedConfig.class).getReturnType(),int.class,"Forge correction descriptor");equal(ForgeConfigSpecAdapter.class.getMethod("correct",CommentedConfig.class).getReturnType(),void.class,"native adapter correction descriptor");
        check(!IConfigSpec.class.isAssignableFrom(ForgeConfigSpec.class),"facade does not implement conflicting native interface");
        fails(UnsupportedOperationException.class,()->ForgeConfigSpecAdapter.register(new ConfigTracker(),new ModContainer("bad"),ForgeModConfig.Type.SERVER,spec,null),"SERVER rejected");
        fails(UnsupportedOperationException.class,()->ForgeConfigSpecAdapter.register(new ConfigTracker(),new ModContainer("bad"),ForgeModConfig.Type.CLIENT,spec,null),"CLIENT rejected");
        var proxy=(IForgeConfigSpec<?>)java.lang.reflect.Proxy.newProxyInstance(IForgeConfigSpec.class.getClassLoader(),new Class[]{IForgeConfigSpec.class},(o,m,args)->null);
        fails(UnsupportedOperationException.class,()->new ForgeConfigSpecAdapter(proxy),"custom spec rejected");
    }
    public static void main(String[] args) throws Exception {
        root=Path.of(System.getProperty("c1.test.root"));check(Files.isDirectory(root),"fresh test root exists");Files.createDirectories(root.resolve("config"));
        lifecycle();creationAndErrors();nativeControls();pinnedOracleAndBoundaries();equal(FileWatcher.defaultInstance().count(),0,"all owner watches disposed");
        System.out.println("C1_CONTRACT_PASS assertions="+assertions+" gameLaunched=false runtimeAccepted=false");
    }
}
