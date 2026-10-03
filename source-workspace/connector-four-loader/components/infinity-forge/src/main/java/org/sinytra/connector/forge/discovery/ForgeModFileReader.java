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
import org.sinytra.connector.locator.OrdinaryAdmissionGate;
import org.sinytra.connector.locator.AdmittedModCatalog;
import org.sinytra.connector.infinity.inventory.AdmissionInventory.*;
import org.sinytra.connector.infinity.inventory.AdmissionSession;
import java.util.List;
import java.util.Optional;
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
            if (!OrdinaryAdmissionGate.allow(contents.getPrimaryPath(), OrdinaryAdmissionGate.root(contents.getPrimaryPath())))
                // IModFileReader null means fall-through, not exclusion. Ordinary root gate handles clean skips.
                throw new IllegalStateException("Excluded nested/alternate Forge candidate requires launch admission manifest filtering: " + contents.getPrimaryPath());
            Forge52JarAdapter.Result result = Forge52JarAdapter.adapt(contents.getPrimaryPath(),
                ConnectorUtil.CONNECTOR_FOLDER.resolve("forge52"), (FMLLoader.getDist().isClient() ? "CLIENT" : "SERVER"));
            AdmissionSession.current().bindDerived(result.output(), contents.getPrimaryPath());
            var derived = new JarContentsBuilder().paths(result.output()).build();
            AdmissionSession.current().bindRuntimeObject(derived, List.of(result.output()));
            IModFile mod = JarModsDotTomlModFileReader.createModFile(derived, attributes.withReader(this));
            LOGGER.info("Unified Forge ABI slice prepared source={} sha256={} derived={} cacheHit={}",
                contents.getPrimaryPath(), result.inputSha256(), result.output(), result.cacheHit());
            AdmissionSession.current().bindRuntimeObject(mod, List.of(result.output()));
            AdmittedModCatalog.captureOriginal(mod, contents.getPrimaryPath(), Ecosystem.FORGE, Lane.FORGE_ADAPTER, Optional.of(result.inputSha256()));
            return mod;
        } catch (IllegalStateException policyError) {
            throw policyError;
        } catch (Exception error) {
            LOGGER.error("Cannot adapt Forge candidate {}: {}", contents.getPrimaryPath(), error.getMessage(), error);
            throw new ModLoadingException(ModLoadingIssue.error("Unified Forge 52 ABI slice rejected candidate: " + error.getMessage())
                .withAffectedPath(contents.getPrimaryPath()).withCause(error));
        }
    }
}
