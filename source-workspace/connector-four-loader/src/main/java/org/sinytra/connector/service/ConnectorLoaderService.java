package org.sinytra.connector.service;

import com.mojang.logging.LogUtils;
import cpw.mods.modlauncher.LaunchPluginHandler;
import cpw.mods.modlauncher.Launcher;
import cpw.mods.modlauncher.api.IEnvironment;
import cpw.mods.modlauncher.api.IModuleLayerManager;
import cpw.mods.modlauncher.api.ITransformationService;
import cpw.mods.modlauncher.api.ITransformer;
import cpw.mods.modlauncher.serviceapi.ILaunchPluginService;
import net.neoforged.fml.loading.LoadingModList;
import org.sinytra.connector.ConnectorEarlyLoader;
import org.sinytra.connector.service.hacks.ConnectorForkJoinThreadFactory;
import org.sinytra.connector.service.hacks.FabricASMFixer;
import org.sinytra.connector.service.hacks.LenientRuntimeEnumExtender;
import org.sinytra.connector.service.hacks.ModuleLayerMigrator;
import org.sinytra.connector.util.ConnectorUtil;
import org.slf4j.Logger;

import java.lang.invoke.VarHandle;
import java.lang.reflect.Field;
import java.nio.file.Path;
import java.util.*;
import java.util.function.*;
import java.util.stream.Stream;

import static cpw.mods.modlauncher.api.LambdaExceptionUtils.uncheck;

public class ConnectorLoaderService implements ITransformationService {
    private static final String NAME = "connector_loader";
    private static final String AUTHLIB_MODULE = "authlib";
    private static final String BRIGADIER_MODULE = "brigadier";
    private static final Logger LOGGER = LogUtils.getLogger();
    private static final VarHandle PLUGINS = uncheck(() -> ConnectorUtil.TRUSTED_LOOKUP.findVarHandle(LaunchPluginHandler.class, "plugins", Map.class));

    @Override
    public String name() {
        return NAME;
    }

    @Override
    public void initialize(IEnvironment environment) {
        ConnectorForkJoinThreadFactory.install();
    }

    /** Called by the FML-owned GAME-layer boundary, never by wrapping a window. */
    public void beforeGameStart(ModuleLayer layer) {
        if (!ConnectorEarlyLoader.hasEncounteredException()) {
            ConnectorEarlyLoader.setup();
            // Keep plugin initialization before any target class can be defined twice.
            uncheck(() -> Class.forName("org.sinytra.connector.mod.DummyTarget", false,
                    Thread.currentThread().getContextClassLoader()));
            ConnectorEarlyLoader.preLaunch();
        }
    }

    @SuppressWarnings("unchecked")
    @Override
    public void onLoad(IEnvironment env, Set<String> otherServices) {
        List<ILaunchPluginService> injectPlugins = List.of(new ConnectorPreLaunchPlugin());

        try {
            Field launchPluginsField = Launcher.class.getDeclaredField("launchPlugins");
            launchPluginsField.setAccessible(true);
            LaunchPluginHandler launchPluginHandler = (LaunchPluginHandler) launchPluginsField.get(Launcher.INSTANCE);
            Map<String, ILaunchPluginService> plugins = (Map<String, ILaunchPluginService>) PLUGINS.get(launchPluginHandler);
            // Sort launch plugins
            LinkedHashMap<String, ILaunchPluginService> sortedPlugins = new LinkedHashMap<>();
            // Mixin must come first
            sortedPlugins.put("mixin", plugins.remove("mixin"));
            // Handle cases where a mixin has already made the enum mutable
            plugins.remove("runtime_enum_extender");
            sortedPlugins.put("runtime_enum_extender", new LenientRuntimeEnumExtender());
            // Our plugins come after mixin
            injectPlugins.forEach(plugin -> sortedPlugins.put(plugin.name(), plugin));
            // The rest goes to the end
            sortedPlugins.putAll(plugins);
            PLUGINS.set(launchPluginHandler, sortedPlugins);
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    @Override
    public List<Resource> completeScan(IModuleLayerManager layerManager) {
        // Ignore default Fabric mod locator warnings
        LoadingModList.get().getModLoadingIssues()
            .removeIf(issue -> {
                Path path = issue.affectedPath();
                return ConnectorEarlyLoader.isConnectorMod(path) && issue.translationKey().startsWith("fml.modloadingissue.brokenfile.");
            });

        // Add our loading errors
        LoadingModList.get().getModLoadingIssues().addAll(ConnectorEarlyLoader.getLoadingExceptions());

        layerManager.getLayer(IModuleLayerManager.Layer.PLUGIN)
            .map(ModuleLayer::modules)
            .ifPresent(modules -> {
                LOGGER.debug("Making PLUGIN modules read connector");
                ModuleLayerMigrator.addReads(modules);
            });

        return List.of(new Resource(
            IModuleLayerManager.Layer.GAME,
            Stream.of(
                    FabricASMFixer.provideGeneratedClassesJar(),
                    ModuleLayerMigrator.moveModule(AUTHLIB_MODULE),
                    ModuleLayerMigrator.moveModule(BRIGADIER_MODULE)
                )
                .filter(Objects::nonNull)
                .toList()
        ));
    }

    @Override
    public List<? extends ITransformer<?>> transformers() {
        return List.of();
    }
}
