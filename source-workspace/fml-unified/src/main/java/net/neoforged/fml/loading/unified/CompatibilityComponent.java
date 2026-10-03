/* Unified Infinity internal source-fusion contract. SPDX-License-Identifier: LGPL-2.1-only */
package net.neoforged.fml.loading.unified;

import cpw.mods.modlauncher.api.*;
import java.util.List;
import java.util.Set;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.neoforgespi.ILaunchContext;
import net.neoforged.neoforgespi.coremod.ICoreMod;
import net.neoforged.neoforgespi.language.IModLanguageLoader;
import net.neoforged.neoforgespi.locating.*;
import org.jetbrains.annotations.ApiStatus;

/** Installed source-owned loader implementation. Never discovered from an external mod SPI. */
@ApiStatus.Internal
public interface CompatibilityComponent {
    default void onLoad(IEnvironment environment, Set<String> otherServices) throws IncompatibleEnvironmentException {}
    default void initialize(IEnvironment environment, ILaunchContext launchContext) {}
    default List<ITransformationService.Resource> beginScanning(IEnvironment environment) { return List.of(); }
    default List<ITransformationService.Resource> completeScan(IModuleLayerManager layers) { return List.of(); }
    default List<? extends ITransformer<?>> transformers() { return List.of(); }
    default List<IModFileCandidateLocator> candidateLocators() { return List.of(); }
    default List<IModFileReader> modFileReaders() { return List.of(); }
    default List<IDependencyLocator> dependencyLocators() { return List.of(); }
    default List<IModLanguageLoader> languageProviders() { return List.of(); }
    default List<ICoreMod> coreMods() { return List.of(); }
    /** Replaces compatibility's old reflective window-provider wrapper at the same FML-owned phase. */
    default void beforeGameStart(ModuleLayer gameLayer, Dist dist) {}
}
