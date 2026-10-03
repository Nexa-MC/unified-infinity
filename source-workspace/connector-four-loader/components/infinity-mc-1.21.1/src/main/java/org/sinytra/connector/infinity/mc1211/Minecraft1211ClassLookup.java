package org.sinytra.connector.infinity.mc1211;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;
import java.util.zip.ZipFile;
import net.neoforged.fml.ModLoadingException;
import net.neoforged.fml.ModLoadingIssue;
import net.neoforged.fml.loading.FMLEnvironment;
import net.neoforged.fml.loading.FMLLoader;
import net.neoforged.fml.loading.LibraryFinder;
import net.neoforged.fml.loading.MavenCoordinate;
import org.sinytra.adapter.util.provider.ClassLookup;
import org.sinytra.adapter.util.provider.ZipClassLookup;
import org.sinytra.connector.infinity.ResourceScope;
import org.sinytra.connector.transformer.jar.SimpleClassLookup;
import net.minecraftforge.fart.api.ClassProvider;
import static cpw.mods.modlauncher.api.LambdaExceptionUtils.uncheck;

/** Pinned Minecraft 1.21.1 clean-bytecode selection; no independent classloader. */
public final class Minecraft1211ClassLookup {
    private Minecraft1211ClassLookup() {}
    public static ClassLookup open(ResourceScope resources) {
        // Adapted from Connector beta17 ConnectorTransformerEnvironment (MIT); selection is unchanged.
        String mcAndNeoFormVersion = FMLLoader.versionInfo().mcAndNeoFormVersion();
        if (FMLEnvironment.production) {
            MavenCoordinate coords = new MavenCoordinate("net.minecraft", FMLEnvironment.dist.isClient() ? "client" : "server", "", "srg", mcAndNeoFormVersion);
            Path path = LibraryFinder.findPathForMaven(coords);
            if (!Files.exists(path)) {
                throw new ModLoadingException(ModLoadingIssue.error("fml.modloadingissue.corrupted_installation").withAffectedPath(path));
            }
            ZipFile zipFile = resources.own(uncheck(() -> new ZipFile(path.toFile())));
            return new ZipClassLookup(zipFile);
        } else {
            Path cleanPath = Optional.ofNullable(System.getProperty("connector.clean.path"))
                .map(Path::of)
                .filter(Files::exists)
                .orElseThrow(() -> new RuntimeException("Could not determine clean minecraft artifact path"));
            return new SimpleClassLookup(resources.own(ClassProvider.fromPaths(cleanPath)));
        }
    }
}
