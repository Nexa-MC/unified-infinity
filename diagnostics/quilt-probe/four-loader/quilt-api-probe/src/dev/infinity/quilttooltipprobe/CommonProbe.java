package dev.infinity.quilttooltipprobe;

import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.Optional;
import net.minecraft.class_1792;
import net.minecraft.class_1799;
import net.minecraft.class_2378;
import net.minecraft.class_2960;
import net.minecraft.class_5632;
import net.minecraft.class_7923;
import org.quiltmc.loader.api.ModContainer;
import org.quiltmc.loader.api.QuiltLoader;
import org.quiltmc.qsl.base.api.entrypoint.ModInitializer;
import org.quiltmc.qsl.base.api.entrypoint.server.DedicatedServerModInitializer;

/** Project-owned common fixture; no client class is used by any common method. */
public final class CommonProbe implements ModInitializer, DedicatedServerModInitializer {
    public static final String ID = "unified-quilt-tooltip-probe";
    public static final String NAMESPACE = "unified_quilt_tooltip_probe";
    public static final String QSL_VERSION = "10.0.0-alpha.5+1.21.1";
    public static class_1792 convertibleItem;
    public static class_1792 plainItem;
    public static int initialized;
    private static int serverInitialized;

    static { System.out.println("NATIVE_QUILT_TOOLTIP_PROBE CLASS_DEFINED"); }

    @Override
    public void onInitialize(ModContainer mod) {
        require(++initialized == 1, "common_init_once");
        require(mod.metadata().id().equals(ID), "original_probe_id");
        require(mod.metadata().group().equals("dev.infinity.probes"), "original_probe_group");
        require(mod.metadata().version().raw().equals("0.1.0+native"), "original_probe_version");
        require(mod.getSourceType() == ModContainer.BasicSourceType.NORMAL_QUILT, "native_probe_provider");
        require(QuiltLoader.getModContainer(ID).orElseThrow() == mod, "probe_provider_identity");
        require(mod.getClassLoader() == getClass().getClassLoader(), "probe_classloader_identity");
        for (String id : new String[] {"quilt_base", "quilt_lifecycle_events", "quilt_tooltip"}) {
            ModContainer provider = QuiltLoader.getModContainer(id).orElseThrow();
            require(provider.metadata().version().raw().equals(QSL_VERSION), "pinned_version_" + id);
            require(QuiltLoader.getAllMods().stream().filter(m -> m.metadata().id().equals(id)).count() == 1,
                    "single_provider_" + id);
            pass("provider", "id=" + id + " version=" + provider.metadata().version().raw()
                    + " type=" + provider.getSourceType() + " sources=" + provider.getSourcePaths());
        }
        convertibleItem = register("convertible", new ConvertibleItem());
        plainItem = register("plain", new class_1792(new class_1792.class_1793()));
        require(new CommonTooltipData("common-data-linkage", false) instanceof class_5632, "common_data_linkage");
        try {
            require(Files.readString(mod.getPath("native-quilt-tooltip-proof.txt"))
                    .equals("original-native-quilt-tooltip-resource\n"), "native_resource");
            Path source = mod.getSourcePaths().get(0).get(0);
            require(Files.isRegularFile(source), "original_probe_source_file");
            String hash = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(source)));
            pass("common_init", "count=1 original_probe=" + source + " sha256=" + hash);
        } catch (Exception e) {
            throw new IllegalStateException("NATIVE_QUILT_TOOLTIP_PROBE source_readback", e);
        }
    }

    @Override
    public void onInitializeServer(ModContainer mod) {
        require(initialized == 1 && ++serverInitialized == 1, "server_init_once");
        // getDeclaredMethods resolves method signatures: an unstripped client return type must fail this gate.
        require(Arrays.stream(CommonTooltipData.class.getDeclaredMethods())
                .noneMatch(method -> method.getName().equals("toComponent")), "implementing_client_method_stripped");
        CommonTooltipData data = new CommonTooltipData("dedicated-server", false);
        require(data.label.equals("dedicated-server") && data.conversions == 0, "common_data_constructed_on_server");
        require(new class_1799(convertibleItem).method_32347().orElseThrow() instanceof CommonTooltipData,
                "common_item_data_on_server");
        pass("server_side_linkage", "common_data=true implementing_client_method=absent");
    }

    private static class_1792 register(String path, class_1792 item) {
        class_2960 id = class_2960.method_60655(NAMESPACE, path);
        require(class_2378.method_10230(class_7923.field_41178, id, item) == item, "register_" + path);
        require(class_7923.field_41178.method_10223(id) == item, "registry_identity_" + path);
        return item;
    }

    public static void require(boolean condition, String name) {
        if (!condition) throw new IllegalStateException("NATIVE_QUILT_TOOLTIP_PROBE FAIL " + name);
    }

    public static void pass(String stage, String detail) {
        System.out.println("NATIVE_QUILT_TOOLTIP_PROBE PASS stage=" + stage + " " + detail);
    }

    public static final class ConvertibleItem extends class_1792 {
        public ConvertibleItem() { super(new class_1792.class_1793()); }

        @Override
        public Optional<class_5632> method_32346(class_1799 stack) {
            return Optional.of(new CommonTooltipData("QSL convertible component", false));
        }
    }
}
