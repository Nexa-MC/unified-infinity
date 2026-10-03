package infinity.probe.forgeconfig.boundary;

import net.minecraftforge.common.ForgeConfigSpec;
import net.minecraftforge.fml.ModContainer;
import net.minecraftforge.fml.ModLoadingContext;
import net.minecraftforge.fml.config.ConfigTracker;
import net.minecraftforge.fml.config.IConfigEvent;
import net.minecraftforge.fml.config.IConfigSpec;
import net.minecraftforge.fml.config.ModConfig;
import net.minecraftforge.fml.event.config.ModConfigEvent;

// Self-authored rejection inputs. Compile against official Forge only, when
// separately authorized. These are not production mods or implementation code.
class RejectedServer {
    static ModConfig.Type use() { return ModConfig.Type.SERVER; }
}
class RejectedClient {
    static ModConfig.Type use() { return ModConfig.Type.CLIENT; }
}
class RejectedLegacyContext {
    static ModLoadingContext use() { return ModLoadingContext.get(); }
}
class RejectedBaseContextRegistration {
    static void use(ModLoadingContext context, ForgeConfigSpec spec) {
        context.registerConfig(ModConfig.Type.COMMON, spec);
    }
}
class RejectedDirectModConfig {
    static ModConfig use(ForgeConfigSpec spec, ModContainer owner) {
        return new ModConfig(ModConfig.Type.COMMON, spec, owner);
    }
}
class RejectedDirectNamedModConfig {
    static ModConfig use(ForgeConfigSpec spec, ModContainer owner) {
        return new ModConfig(ModConfig.Type.COMMON, spec, owner, "direct.toml");
    }
}
class RejectedRawConfigData {
    static Object use(ModConfig config) { return config.getConfigData(); }
}
class RejectedRawSpecData {
    static Object use(ForgeConfigSpec spec) { return spec.getValues(); }
}
class RejectedTracker {
    static Object use() { return ConfigTracker.INSTANCE.fileMap(); }
}
abstract class RejectedCustomSpec implements IConfigSpec<RejectedCustomSpec> {}
class RejectedBuilderSubclass extends ForgeConfigSpec.Builder {}
class RejectedModConfigSubclass extends ModConfig {
    RejectedModConfigSubclass(ForgeConfigSpec spec, ModContainer owner) {
        super(ModConfig.Type.COMMON, spec, owner);
    }
}
class RejectedEnumValues {
    static ModConfig.Type[] use() { return ModConfig.Type.values(); }
}
class RejectedEnumValueOf {
    static ModConfig.Type use() { return ModConfig.Type.valueOf("COMMON"); }
}
class RejectedUnloading {
    static ModConfig use(ModConfigEvent.Unloading event) { return event.getConfig(); }
}
class RejectedBaseEventGetter {
    static ModConfig use(ModConfigEvent event) { return event.getConfig(); }
}
class RejectedInterfaceEventGetter {
    static ModConfig use(IConfigEvent event) { return event.getConfig(); }
}
class RejectedLoadingConstruction {
    static ModConfigEvent.Loading use(ModConfig config) { return new ModConfigEvent.Loading(config); }
}
class RejectedSpecContractCall {
    static void use(IConfigSpec<?> spec) { spec.afterReload(); }
}
class RejectedBuilderOverload {
    static ForgeConfigSpec.Builder use(ForgeConfigSpec.Builder builder) {
        return builder.comment("first", "second");
    }
}
class RejectedBooleanSaveAlias {
    static void use(ForgeConfigSpec.BooleanValue value) { value.save(); }
}
class RejectedConfigValueSaveAlias {
    static void use(ForgeConfigSpec.ConfigValue<?> value) { value.save(); }
}
