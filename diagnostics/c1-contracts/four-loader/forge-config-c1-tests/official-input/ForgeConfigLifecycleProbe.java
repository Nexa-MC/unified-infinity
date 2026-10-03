package infinity.probe.forgeconfig;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;
import net.minecraftforge.common.ForgeConfigSpec;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.config.ModConfig;
import net.minecraftforge.fml.event.config.ModConfigEvent;
import net.minecraftforge.fml.event.lifecycle.FMLCommonSetupEvent;
import net.minecraftforge.fml.javafmlmod.FMLJavaModLoadingContext;

/**
 * Self-authored external Forge input for the proposed C1 tranche.
 * Audit artifact only: not compiled, transformed, launched or admitted.
 * A future harness compiles this against pinned Forge 52.1.0, not facade classes.
 * The compatibility implementation must not itself be an ordinary @Mod.
 */
@Mod(ForgeConfigLifecycleProbe.MOD_ID)
public final class ForgeConfigLifecycleProbe {
    public static final String MOD_ID = "infinity_forge_config_probe";
    public static final String FILE_NAME = "infinity-forge-config-probe.toml";

    private static final ForgeConfigSpec.Builder BUILDER = new ForgeConfigSpec.Builder();
    public static final ForgeConfigSpec.BooleanValue ENABLED;
    public static final ForgeConfigSpec.IntValue LIMIT;
    public static final ForgeConfigSpec.IntValue RESTART_VALUE;
    public static final ForgeConfigSpec.ConfigValue<String> LABEL;
    public static final ForgeConfigSpec.ConfigValue<List<? extends String>> TAGS;
    public static final ForgeConfigSpec SPEC;
    public static final List<Observation> OBSERVATIONS = new CopyOnWriteArrayList<>();
    public static volatile String constructorRead;
    public static volatile boolean saveDuringLoadingReturned;
    private static final AtomicInteger SEQUENCE = new AtomicInteger();

    static {
        BUILDER.comment("Probe section").translation("infinity.probe.config").push("probe");
        ENABLED = BUILDER.comment("Enable probe").define("enabled", true);
        LIMIT = BUILDER.comment("Bounded probe value").defineInRange("limit", 4, 1, 9);
        RESTART_VALUE = BUILDER.worldRestart().defineInRange("restartValue", 2, 0, 9);
        LABEL = BUILDER.define("label", "seed");
        TAGS = BUILDER.defineListAllowEmpty("tags", List.of("safe"), value -> value instanceof String);
        BUILDER.pop();
        SPEC = BUILDER.build();
    }

    public ForgeConfigLifecycleProbe(FMLJavaModLoadingContext context) {
        context.getModEventBus().addListener(ForgeConfigLifecycleProbe::onLoading);
        context.getModEventBus().addListener(ForgeConfigLifecycleProbe::onReloading);
        context.getModEventBus().addListener(ForgeConfigLifecycleProbe::onSetup);

        try {
            constructorRead = "value:" + LIMIT.get();
        } catch (RuntimeException failure) {
            constructorRead = "exception:" + failure.getClass().getName();
        }

        if (Boolean.getBoolean("infinity.probe.config.defaultName")) {
            context.registerConfig(ModConfig.Type.COMMON, SPEC);
        } else {
            context.registerConfig(ModConfig.Type.COMMON, SPEC, FILE_NAME);
        }
        context.registerConfig(ModConfig.Type.COMMON, new ForgeConfigSpec.Builder().build(),
            "infinity-empty-config-must-not-exist.toml");
    }

    private static void onLoading(ModConfigEvent.Loading event) {
        observe("LOADING", event.getConfig());
        if (Boolean.getBoolean("infinity.probe.config.saveDuringLoading")) {
            SPEC.save();
            saveDuringLoadingReturned = true;
        }
    }

    private static void onReloading(ModConfigEvent.Reloading event) {
        observe("RELOADING", event.getConfig());
    }

    private static void onSetup(FMLCommonSetupEvent ignored) {
        observe("COMMON_SETUP", null);
    }

    private static void observe(String phase, ModConfig config) {
        boolean originalSpec = config == null || config.getSpec() == SPEC;
        OBSERVATIONS.add(new Observation(SEQUENCE.incrementAndGet(), phase,
            Thread.currentThread().getName(), Thread.currentThread().getContextClassLoader(),
            SPEC.isLoaded(), originalSpec,
            config == null ? null : config.getType(),
            config == null ? null : config.getFileName(),
            config == null ? null : config.getModId(),
            ENABLED.get(), LIMIT.get(), RESTART_VALUE.get(), LABEL.get(), List.copyOf(TAGS.get())));
    }

    /** Future harness invokes outside an event callback, then independently reads disk. */
    public static void mutateWithoutExplicitSave() {
        ENABLED.set(false);
        LIMIT.set(6);
        RESTART_VALUE.set(7);
        LABEL.set("saved");
        TAGS.set(List.of("kept", "saved"));
    }

    /** Both public save paths must resolve to the same owner and file. */
    public static void saveThroughSpec() {
        SPEC.save();
    }

    public static void saveThroughValue() {
        LIMIT.save();
    }

    public record Observation(int sequence, String phase, String threadName, ClassLoader contextLoader,
                              boolean loaded, boolean originalSpec, ModConfig.Type type,
                              String fileName, String modId, boolean enabled, int limit,
                              int restartValue, String label, List<?> tags) {}
}
