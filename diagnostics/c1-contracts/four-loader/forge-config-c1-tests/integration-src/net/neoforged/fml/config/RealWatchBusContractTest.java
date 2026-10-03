package net.neoforged.fml.config;

import java.lang.reflect.Proxy;
import java.nio.file.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import net.neoforged.bus.api.*;
import net.neoforged.fml.ModContainer;
import net.neoforged.fml.event.IModBusEvent;
import net.neoforged.neoforgespi.language.IModInfo;
import com.electronwill.nightconfig.core.file.FileWatcher;
import com.electronwill.nightconfig.toml.*;
import org.sinytra.connector.forge.config.*;

/** Real native final acceptEvent, bus8.0.5, NightConfig3.8.3 watcher and OS file events. */
public final class RealWatchBusContractTest {
    static int assertions;
    static void check(boolean ok,String why){assertions++;if(!ok)throw new AssertionError(why);}
    static final class Container extends ModContainer {
        final IEventBus bus=BusBuilder.builder().markerType(IModBusEvent.class).allowPerPhasePost().build();
        Container(String id){super((IModInfo)Proxy.newProxyInstance(IModInfo.class.getClassLoader(),new Class[]{IModInfo.class},(p,m,a)->switch(m.getName()){
            case "getModId","getNamespace","getDisplayName" -> id;
            case "getVersion" -> new org.apache.maven.artifact.versioning.DefaultArtifactVersion("1");
            default -> null;
        }));}
        @Override public IEventBus getEventBus(){return bus;}
    }
    public static void main(String[] args)throws Exception {
        var root=Path.of(System.getProperty("c1.test.root"));var directory=root.resolve("config");Files.createDirectories(directory);
        var tracker=new ConfigTracker();var owner=new Container("real_watch");
        String watcherSource=FileWatcher.class.getProtectionDomain().getCodeSource().getLocation().toString();
        String containerSource=ModContainer.class.getProtectionDomain().getCodeSource().getLocation().toString();
        String busSource=owner.bus.getClass().getProtectionDomain().getCodeSource().getLocation().toString();
        check(watcherSource.endsWith("core-3.8.3.jar"),"real pinned watcher CodeSource");
        check(containerSource.endsWith("frozen-inputs/fml.jar"),"real frozen native ModContainer CodeSource");
        check(busSource.endsWith("bus-8.0.5.jar"),"real pinned event bus CodeSource");
        check(java.util.Arrays.stream(FileWatcher.class.getDeclaredMethods()).noneMatch(m->m.getName().equals("fire")||m.getName().equals("count")),"deterministic watcher stub absent");
        System.out.println("REAL_CODESOURCES FileWatcher="+watcherSource+" ModContainer="+containerSource+" EventBus="+busSource+" busClass="+owner.bus.getClass().getName());
        var b=new ForgeConfigSpec.Builder();
        var value=b.worldRestart().defineInRange("value",2,0,9);var spec=b.build();var loading=new AtomicInteger();var reloading=new AtomicInteger();
        var nativeEvents=new AtomicInteger();var seven=new CountDownLatch(1);var eight=new CountDownLatch(1);var failure=new AtomicReference<Throwable>();var identity=new AtomicReference<ForgeModConfig>();
        owner.bus.addListener((ForgeModConfigEvent.Loading event)->{
            check(spec.isLoaded(),"loaded before real-bus Loading");check(event.getConfig().getSpec()==spec,"real-bus original spec");identity.set(event.getConfig());
            loading.incrementAndGet();int before=reloading.get();spec.save();check(reloading.get()==before,"real-bus save during Loading has no recursive Reloading");
        });
        owner.bus.addListener((ForgeModConfigEvent.Reloading event)->{
            try {
                check(event.getConfig()==identity.get(),"real watcher stable facade");check(event.getConfig().getSpec()==spec,"real watcher original spec");
                reloading.incrementAndGet();int current=value.get();if(current==7)seven.countDown();if(current==8)eight.countDown();
            }catch(Throwable t){failure.set(t);seven.countDown();eight.countDown();}
        });
        owner.bus.addListener((net.neoforged.fml.event.config.ModConfigEvent event)->nativeEvents.incrementAndGet());
        ForgeConfigSpecAdapter.register(tracker,owner,ForgeModConfig.Type.COMMON,spec,"watch.toml");
        try {
            tracker.loadConfigs(ModConfig.Type.COMMON,directory);check(loading.get()==1,"one real-bus Loading");check(value.get()==2,"cache seeded");
            // Native addWatch queues registration. A same-filesystem no-op removal future
            // is a supported control-queue barrier; it adds no watch and changes no owner.
            FileWatcher.defaultInstance().removeWatchFuture(directory.resolve("never-watched-barrier.toml")).get(10,TimeUnit.SECONDS);
            var file=directory.resolve("watch.toml");var config=new TomlParser().parse(Files.newBufferedReader(file));config.set("value",7);
            new TomlWriter().write(config,file,com.electronwill.nightconfig.core.io.WritingMode.REPLACE_ATOMIC);
            check(seven.await(15,TimeUnit.SECONDS),"real watcher sees external atomic-write transition to7");
            check(failure.get()==null,"watch listener succeeded: "+failure.get());check(value.get()==7,"real callback invalidates worldRestart cache");
            value.set(8);check(new TomlParser().parse(Files.newBufferedReader(file)).getInt("value")==8,"real watcher path autosave persisted");
            check(eight.await(15,TimeUnit.SECONDS),"real watcher eventually sees autosave transition to8");
            check(nativeEvents.get()==0,"Forge registration never receives native event family");check(failure.get()==null,"all bus callbacks succeeded");
        }finally {
            tracker.unloadConfigs(ModConfig.Type.COMMON);
            FileWatcher.defaultInstance().stopFuture().get(10,TimeUnit.SECONDS);
        }
        check(!spec.isLoaded(),"owner disposal clears state");
        System.out.println("C1_REAL_WATCH_BUS_PASS assertions="+assertions+" observedReloads="+reloading.get()+" gameLaunched=false");
    }
}
