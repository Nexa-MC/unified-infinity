package net.neoforged.fml.config;

import java.nio.file.*;
import com.electronwill.nightconfig.core.file.CommentedFileConfig;
import com.electronwill.nightconfig.core.io.WritingMode;
import net.neoforged.fml.ModContainer;
import org.sinytra.connector.forge.config.*;

/** Compares pinned Forge synchronous-autosave exception/cache ordering using temporary paths only. */
public final class FailureOrderingTest {
    record Result(String exception,int cached,int raw,String preservedDisk) {}
    static Path obstruct(Path directory)throws Exception {
        Path moved=directory.resolveSibling(directory.getFileName()+"-moved");Files.move(directory,moved);
        Files.writeString(directory,"temporary non-directory parent");return moved;
    }
    static void restore(Path directory,Path moved)throws Exception {Files.delete(directory);Files.move(moved,directory);}
    static Result official(Path directory)throws Exception {
        Files.createDirectories(directory);Path file=directory.resolve("config.toml");
        var b=new net.minecraftforge.common.ForgeConfigSpec.Builder();var value=b.defineInRange("value",4,0,9);var spec=b.build();
        try(var data=CommentedFileConfig.builder(file).sync().autosave().writingMode(WritingMode.REPLACE).build()) {
            data.load();spec.acceptConfig(data);if(value.get()!=4)throw new AssertionError("official cache seed");
            Path moved=obstruct(directory);
            try {
                Throwable error=null;try{value.set(6);}catch(Throwable t){error=t;}
                if(error==null)throw new AssertionError("official save should fail");
                return new Result(error.getClass().getName(),value.get(),data.getInt("value"),Files.readString(moved.resolve("config.toml")));
            }finally{restore(directory,moved);}
        }
    }
    static Result candidate(Path directory)throws Exception {
        var b=new ForgeConfigSpec.Builder();var value=b.defineInRange("value",4,0,9);var spec=b.build();
        var tracker=new ConfigTracker();var owner=new ModContainer("failure_order");
        ForgeConfigSpecAdapter.register(tracker,owner,ForgeModConfig.Type.COMMON,spec,"config.toml");tracker.loadConfigs(ModConfig.Type.COMMON,directory);
        if(value.get()!=4)throw new AssertionError("candidate cache seed");
        Path moved=obstruct(directory);
        try {
            Throwable error=null;try{value.set(6);}catch(Throwable t){error=t;}
            if(error==null)throw new AssertionError("candidate save should fail");
            int raw=tracker.fileMap.get("config.toml").getLoadedConfig().config().getInt("value");
            return new Result(error.getClass().getName(),value.get(),raw,Files.readString(moved.resolve("config.toml")));
        }finally{restore(directory,moved);tracker.unloadConfigs(ModConfig.Type.COMMON);}
    }
    public static void main(String[] args)throws Exception {
        Path root=Path.of(System.getProperty("c1.test.root"));var original=official(root.resolve("original"));var current=candidate(root.resolve("candidate"));
        System.out.println("OFFICIAL_FAILURE_ORDER "+original);System.out.println("CANDIDATE_FAILURE_ORDER "+current);
        if(!original.equals(current))throw new AssertionError("Synchronous-save exception/cache/raw/disk ordering differs from pinned Forge");
        if(current.cached()!=4||current.raw()!=6)throw new AssertionError("Expected retained old cache and mutated raw data after failed autosave");
        System.out.println("C1_FAILURE_ORDER_PASS cache=4 raw=6 persisted=4");
    }
}
