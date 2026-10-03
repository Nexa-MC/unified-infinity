package org.sinytra.connector.infinity;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Collection;
import java.util.Optional;
import java.util.zip.ZipFile;
import net.neoforged.fml.ModLoadingException;
import net.neoforged.fml.ModLoadingIssue;
import net.neoforged.fml.loading.FMLEnvironment;
import net.neoforged.fml.loading.FMLLoader;
import net.neoforged.fml.loading.LibraryFinder;
import net.neoforged.fml.loading.MavenCoordinate;
import net.neoforged.neoforgespi.locating.IModFile;
import org.sinytra.adapter.util.provider.ClassLookup;
import org.sinytra.adapter.util.provider.ZipClassLookup;
import org.sinytra.connector.locator.transform.ConnectorTransformerEnvironment;
import org.sinytra.connector.transformer.jar.SimpleClassLookup;
import reloc.net.minecraftforge.fart.api.ClassProvider;
import static cpw.mods.modlauncher.api.LambdaExceptionUtils.uncheck;

/** Same pinned upstream lookup selection, with explicit ownership of newly created handles. */
public final class ManagedConnectorTransformerEnvironment extends ConnectorTransformerEnvironment implements AutoCloseable {
    private final ResourceScope resources = new ResourceScope();

    public ManagedConnectorTransformerEnvironment(Collection<IModFile> loadedModFiles) {
        super(loadedModFiles);
    }

    @Override
    public String getJarCacheVersion() {
        return super.getJarCacheVersion() + BuildIdentity.TRANSFORM_CACHE_SUFFIX;
    }

    @Override
    public ClassLookup getCleanClassLookup() {
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

    @Override
    public void close() {
        resources.close();
    }
}
