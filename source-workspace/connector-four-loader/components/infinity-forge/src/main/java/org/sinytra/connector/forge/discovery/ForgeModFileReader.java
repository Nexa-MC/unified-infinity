package org.sinytra.connector.forge.discovery;

import cpw.mods.jarhandling.JarContents;
import cpw.mods.jarhandling.JarContentsBuilder;
import net.neoforged.fml.ModLoadingException;
import net.neoforged.fml.ModLoadingIssue;
import net.neoforged.fml.loading.FMLLoader;
import net.neoforged.fml.loading.moddiscovery.readers.JarModsDotTomlModFileReader;
import net.neoforged.neoforgespi.locating.IModFile;
import net.neoforged.neoforgespi.locating.IModFileReader;
import net.neoforged.neoforgespi.locating.ModFileDiscoveryAttributes;
import org.sinytra.connector.util.ConnectorUtil;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** Joins FML's original reader transaction before its incompatible-Forge fallback. */
public final class ForgeModFileReader implements IModFileReader {
    private static final Logger LOGGER = LoggerFactory.getLogger(ForgeModFileReader.class);

    @Override public int getPriority() { return 1000; }

    @Override public IModFile read(JarContents contents, ModFileDiscoveryAttributes attributes) {
        if (contents.findFile(Forge52JarAdapter.SOURCE_TOML).isEmpty()) return null;
        // Native Neo metadata is authoritative for already dual-packaged native mods.
        // This reader never rewrites or advertises those as Forge-adapted inputs.
        if (contents.findFile(Forge52JarAdapter.TARGET_TOML).isPresent()) return null;
        try {
            Forge52JarAdapter.Result result = Forge52JarAdapter.adapt(contents.getPrimaryPath(),
                ConnectorUtil.CONNECTOR_FOLDER.resolve("forge52"), (FMLLoader.getDist().isClient() ? "CLIENT" : "SERVER"));
            var derived = new JarContentsBuilder().paths(result.output()).build();
            IModFile mod = JarModsDotTomlModFileReader.createModFile(derived, attributes.withReader(this));
            LOGGER.info("Unified Forge ABI slice prepared source={} sha256={} derived={} cacheHit={}",
                contents.getPrimaryPath(), result.inputSha256(), result.output(), result.cacheHit());
            return mod;
        } catch (Exception error) {
            LOGGER.error("Cannot adapt Forge candidate {}: {}", contents.getPrimaryPath(), error.getMessage(), error);
            throw new ModLoadingException(ModLoadingIssue.error("Unified Forge 52 ABI slice rejected candidate: " + error.getMessage())
                .withAffectedPath(contents.getPrimaryPath()).withCause(error));
        }
    }
}
