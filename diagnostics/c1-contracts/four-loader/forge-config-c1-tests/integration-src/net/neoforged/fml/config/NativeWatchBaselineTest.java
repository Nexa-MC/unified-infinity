package net.neoforged.fml.config;

import java.lang.reflect.Proxy;
import java.nio.file.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import com.electronwill.nightconfig.core.file.FileWatcher;
import com.electronwill.nightconfig.toml.*;
import net.neoforged.bus.api.*;
import net.neoforged.fml.ModContainer;
import net.neoforged.fml.event.IModBusEvent;
import net.neoforged.fml.event.config.ModConfigEvent;
import net.neoforged.neoforgespi.language.IModInfo;
import net.neoforged.neoforge.common.ModConfigSpec;

/** Executed with frozen, unmodified fml.jar owner classes and the real watcher/bus. */
public final class NativeWatchBaselineTest {
    static final class Container extends ModContainer {
        final IEventBus bus=BusBuilder.builder().markerType(IModBusEvent.class).allowPerPhasePost().build();
        Container(){super((IModInfo)Proxy.newProxyInstance(IModInfo.class.getClassLoader(),new Class[]{IModInfo.class},(p,m,a)->switch(m.getName()){
            case "getModId","getNamespace","getDisplayName"->"native_baseline";
            case "getVersion"->new org.apache.maven.artifact.versioning.DefaultArtifactVersion("1");
            default->null;
        }));}
        @Override public IEventBus getEventBus(){return bus;}
    }
    public static void main(String[] args)throws Exception {
        boolean barrier=Boolean.parseBoolean(args[0]);var dir=Path.of(System.getProperty("c1.test.root")).resolve("config");Files.createDirectories(dir);
        var tracker=new ConfigTracker();var owner=new Container();var b=new ModConfigSpec.Builder();var value=b.defineInRange("value",2,0,9);var spec=b.build();var transition=new CountDownLatch(1);var events=new AtomicInteger();
        owner.bus.addListener((ModConfigEvent.Reloading event)->{events.incrementAndGet();if(value.get()==7)transition.countDown();});
        tracker.registerConfig(ModConfig.Type.COMMON,spec,owner,"baseline.toml");boolean observed;
        try {
            tracker.loadConfigs(ModConfig.Type.COMMON,dir);if(value.get()!=2)throw new AssertionError("Native initial load failed");
            if(barrier)FileWatcher.defaultInstance().removeWatchFuture(dir.resolve("never-watched-barrier.toml")).get(10,TimeUnit.SECONDS);
            var file=dir.resolve("baseline.toml");var data=new TomlParser().parse(Files.newBufferedReader(file));data.set("value",7);new TomlWriter().write(data,file,com.electronwill.nightconfig.core.io.WritingMode.REPLACE_ATOMIC);
            observed=transition.await(15,TimeUnit.SECONDS);
            if(barrier&&!observed)throw new AssertionError("Native watcher failed after acknowledged readiness");
        }finally{tracker.unloadConfigs(ModConfig.Type.COMMON);FileWatcher.defaultInstance().stopFuture().get(10,TimeUnit.SECONDS);}
        System.out.println("NATIVE_BASELINE_OBSERVATION barrier="+barrier+" observed="+observed+" reloadEvents="+events.get()+" owner="+ConfigTracker.class.getProtectionDomain().getCodeSource().getLocation()+" gameLaunched=false");
    }
}
