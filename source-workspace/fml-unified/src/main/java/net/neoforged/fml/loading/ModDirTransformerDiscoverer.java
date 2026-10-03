/*
 * Copyright (c) Forge Development LLC and contributors
 * SPDX-License-Identifier: LGPL-2.1-only
 * Modified 2026-10-03 for Unified Infinity: frozen pre-service admission origins.
 */

package net.neoforged.fml.loading;

import org.sinytra.connector.infinity.inventory.AdmissionSession;
import org.sinytra.connector.infinity.inventory.BootstrapInstallation;
import com.mojang.logging.LogUtils;
import cpw.mods.modlauncher.api.LambdaExceptionUtils;
import cpw.mods.modlauncher.api.NamedPath;
import cpw.mods.modlauncher.serviceapi.ITransformerDiscoveryService;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import org.slf4j.Logger;

public class ModDirTransformerDiscoverer implements ITransformerDiscoveryService {
    private static final Logger LOGGER = LogUtils.getLogger();
    private UncheckedIOException alreadyFailed;

    @Override
    public List<NamedPath> candidates(final Path gameDirectory, final String launchTarget) {
        try {
            BootstrapInstallation.open(gameDirectory, launchTarget);
            FMLPaths.loadAbsolutePaths(gameDirectory);
            FMLConfig.load();
            return candidates(gameDirectory);
        } catch (UncheckedIOException e) {
            // we capture any error here and then return an empty list so we can
            // show an error in earlyInitialization which fires next
            this.alreadyFailed = e;
            return List.of();
        }
    }

    @Override
    public void earlyInitialization(final String launchTarget, final String[] arguments) {
        if (this.alreadyFailed != null) {
            String errorCause;
            if (this.alreadyFailed.getCause() instanceof FileAlreadyExistsException faee) {
                errorCause = "File already exists: " + faee.getFile() + "\nYou need to move this out of the way, so we can put a directory there.";
            } else if (this.alreadyFailed.getCause() instanceof AccessDeniedException ade) {
                errorCause = "Access denied trying to create a file or directory " + ade.getMessage() + "\nThe game directory is probably read-only. Check the write permission on it.";
            } else {
                errorCause = "An unexpected IO error occurred trying to setup the game directory\n" + this.alreadyFailed.getCause().getMessage();
            }
            LOGGER.error("Admission/setup failed before any early window provider was initialized: {}", errorCause);
            throw this.alreadyFailed;
        }
        ImmediateWindowHandler.load(launchTarget, arguments);
    }

    @Override
    public List<NamedPath> candidates(final Path gameDirectory) {
        scan(gameDirectory);
        return List.copyOf(found);
    }

    private final static List<NamedPath> found = new ArrayList<>();

    public static List<Path> allExcluded() {
        return found.stream().map(np -> np.paths()[0]).toList();
    }

    private static void scan(final Path gameDirectory) {
        // One frozen folder view. Denied bytes never reach FML provider inspection or SERVICE NamedPath.
        found.clear();
        for (Path component : AdmissionSession.current().installedComponents("ADMISSION_CONSUMER"))
            found.add(new NamedPath("unified-installed-compatibility", component));
        for (Path path : AdmissionSession.current().admittedFolder(gameDirectory.resolve(FMLPaths.MODSDIR.relative()))) {
            if (shouldLoadInServiceLayer(path)) found.add(new NamedPath(path.getFileName().toString(), path));
        }
    }

    private static boolean shouldLoadInServiceLayer(Path path) {
        if (!Files.isRegularFile(path)) return false;
        if (!path.toString().endsWith(".jar")) return false;
        if (LambdaExceptionUtils.uncheck(() -> Files.size(path)) == 0) return false;

        return TransformerDiscovererConstants.shouldLoadInServiceLayer(path);
    }
}
