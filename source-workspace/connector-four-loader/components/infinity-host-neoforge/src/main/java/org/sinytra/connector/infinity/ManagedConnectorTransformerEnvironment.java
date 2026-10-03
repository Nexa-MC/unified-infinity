package org.sinytra.connector.infinity;

import java.util.Collection;
import net.neoforged.neoforgespi.locating.IModFile;
import org.sinytra.adapter.util.provider.ClassLookup;
import org.sinytra.connector.locator.transform.ConnectorTransformerEnvironment;

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
        return org.sinytra.connector.infinity.mc1211.Minecraft1211ClassLookup.open(resources);
    }

    @Override
    public void close() {
        resources.close();
    }
}
