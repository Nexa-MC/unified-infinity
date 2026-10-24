package dev.infinity.quiltprobe;

import org.quiltmc.loader.api.ModContainer;
import org.quiltmc.loader.api.QuiltLoader;
import org.quiltmc.loader.api.entrypoint.PreLaunchEntrypoint;
import org.quiltmc.qsl.base.api.entrypoint.ModInitializer;
import org.quiltmc.qsl.base.api.entrypoint.server.DedicatedServerModInitializer;
import org.quiltmc.qsl.lifecycle.api.event.ServerLifecycleEvents;
import org.quiltmc.qsl.lifecycle.api.event.ServerTickEvents;
import net.minecraft.class_1792;
import net.minecraft.class_2378;
import net.minecraft.class_2960;
import net.minecraft.class_7923;
import net.minecraft.class_18;
import net.minecraft.class_2487;
import net.minecraft.class_7225;
import net.minecraft.server.MinecraftServer;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.HexFormat;

/** Native Quilt ABI fixture, compiled against official Loader/QSL and intermediary game types. */
public final class QuiltProbe implements PreLaunchEntrypoint, ModInitializer, DedicatedServerModInitializer {
    static { System.out.println("NATIVE_QUILT_PROBE CLASS_DEFINED"); }
    public static final String ID = "unified-quilt-probe";
    private static int preLaunch, initialized, afterInitialized, sideInitialized, ticks, automaticReady;
    public static int mixinTicks;
    private static class_1792 item;
    private static MinecraftServer readyServer;
    private static final String MARKER = "native_quilt_qsl_alpha5_v1";

    @Override public void onPreLaunch(ModContainer mod) {
        require(++preLaunch == 1, "pre_launch_once");
        verifyContainer(mod);
        try {
            require(Files.readString(mod.getPath("native-quilt-proof.txt")).equals("original-native-quilt-resource\n"), "native_resource");
            Path source = mod.getSourcePaths().get(0).get(0);
            require(Files.isRegularFile(source), "original_source_file");
            String sha = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(source)));
            pass("pre_launch", "count=1 native_id=" + mod.metadata().id() + " group=" + mod.metadata().group() + " version=" + mod.metadata().version().raw() + " source=" + source + " sha256=" + sha);
        } catch (Exception e) { throw new IllegalStateException(e); }
    }
    @Override public void onInitialize(ModContainer mod) {
        require(preLaunch == 1 && ++initialized == 1, "init_after_pre_launch_once");
        verifyContainer(mod);
        class_2960 id = class_2960.method_60655("unified_quilt_probe", "anchor");
        item = new class_1792(new class_1792.class_1793());
        require(class_2378.method_10230(class_7923.field_41178, id, item) == item, "registry_registration");
        verifyRegistry();
        ServerLifecycleEvents.READY.register(server -> {
            require(readyServer == null && ticks == 0, "ready_once_before_tick");
            readyServer = server;
            verifyRegistry();
            ProbeData data = server.method_30002().method_17983().method_17924(ProbeData.FACTORY, "unified_quilt_probe");
            String phase = System.getProperty("unified.quiltProbe.phase", "unset");
            if (phase.equals("create")) {
                require(data.marker.isEmpty(), "create_requires_new_world");
                data.marker = MARKER; data.method_80();
            } else if (phase.equals("reopen")) require(MARKER.equals(data.marker), "saved_data_reopen_before_write");
            else throw new IllegalStateException("Set unified.quiltProbe.phase=create or reopen");
            pass("ready", "phase=" + phase + " marker=" + data.marker + " read_before_write=" + phase.equals("reopen"));
        });
        ServerTickEvents.END.register(server -> {
            require(server == readyServer, "tick_after_ready_same_server");
            if (++ticks == 5) {
                require(automaticReady == 1, "qsl_automatic_event_entrypoint");
                require(mixinTicks >= 5, "host_mixin_real_tick_sentinel");
                require(sideInitialized == 1 && afterInitialized == 1, "native_entrypoints_once");
                verifyRegistry();
                pass("ready_to_save", "ticks=5 mixin_ticks=" + mixinTicks + " auto_ready=" + automaticReady + " phase=" + System.getProperty("unified.quiltProbe.phase"));
            }
        });
        ServerLifecycleEvents.STOPPED.register(server -> pass("stopped", "ticks=" + ticks));
        pass("init", "count=1 registry=unified_quilt_probe:anchor");
    }
    public static void afterInit(ModContainer mod) {
        require(initialized == 1 && ++afterInitialized == 1, "method_reference_order");
        verifyContainer(mod); pass("method_reference", "count=1 order=after_init");
    }
    @Override public void onInitializeServer(ModContainer mod) {
        require(initialized == 1 && ++sideInitialized == 1, "server_init_once_after_init");
        verifyContainer(mod); pass("server_init", "count=1");
    }
    private static void verifyContainer(ModContainer mod) {
        require(mod.metadata().id().equals(ID), "original_id_not_jpms_normalized");
        require(mod.metadata().group().equals("dev.infinity.probes"), "native_group");
        require(mod.metadata().version().raw().equals("0.1.0+native"), "raw_version");
        require(mod.getSourceType() == ModContainer.BasicSourceType.NORMAL_QUILT, "native_source_type");
        require(mod.getClassLoader() == QuiltProbe.class.getClassLoader(), "same_host_classloader");
        require(QuiltLoader.getModContainer(ID).orElseThrow().metadata().id().equals(ID), "quilt_lookup");
        require(QuiltLoader.isModLoaded("quilt_base") && QuiltLoader.isModLoaded("quilt_lifecycle_events"), "managed_qsl_modules");
        require(QuiltLoader.getAllMods().stream().filter(m -> m.metadata().id().equals(ID)).count() == 1, "one_native_container");
    }
    private static void verifyRegistry() {
        require(class_7923.field_41178.method_10223(class_2960.method_60655("unified_quilt_probe", "anchor")) == item, "single_registry_identity");
    }
    public static void require(boolean condition, String name) { if (!condition) throw new IllegalStateException("NATIVE_QUILT_PROBE FAIL " + name); }
    public static void pass(String stage, String detail) { System.out.println("NATIVE_QUILT_PROBE PASS stage=" + stage + " " + detail); }
    public static final class AutomaticEvents implements ServerLifecycleEvents.Ready {
        @Override public void readyServer(MinecraftServer server) { require(++automaticReady == 1, "automatic_event_once"); pass("automatic_ready", "count=1"); }
    }
    public static final class ProbeData extends class_18 {
        // Vanilla 1.21.1 requires a non-null SavedData type on reopen. This fixed-version
        // fixture uses SAVED_DATA_COMMAND_STORAGE; cross-version DFU migration is not claimed.
        static final class_18.class_8645<ProbeData> FACTORY = new class_18.class_8645<>(ProbeData::new, ProbeData::read, net.minecraft.class_4284.field_45077);
        String marker = "";
        static ProbeData read(class_2487 tag, class_7225.class_7874 registry) { ProbeData data = new ProbeData(); data.marker = tag.method_10558("marker"); return data; }
        @Override public class_2487 method_75(class_2487 tag, class_7225.class_7874 registry) { tag.method_10582("marker", marker); return tag; }
    }
}
