package org.sinytra.connector.locator;

import net.neoforged.fml.loading.FMLPaths;
import org.sinytra.connector.infinity.inventory.AdmissionInventory.Ecosystem;
import org.sinytra.connector.infinity.inventory.AdmissionSession;
import java.nio.file.Path;
import java.util.stream.Stream;

/** Fabric/Quilt roots come from the same pre-SERVICE admitted session as native host candidates. */
public final class FabricModsDiscoverer {
    private FabricModsDiscoverer() {}
    public static Stream<Path> scanFabricMods() {
        AdmissionSession session = AdmissionSession.current();
        return session.admittedFolder(FMLPaths.MODSDIR.get()).stream().filter(path -> {
            Ecosystem ecosystem = session.scan(path).orElseThrow().candidate().ecosystem();
            return ecosystem == Ecosystem.FABRIC || ecosystem == Ecosystem.QUILT;
        });
    }
}
