package org.sinytra.connector.locator;

import cpw.mods.jarhandling.JarContents;
import org.sinytra.connector.infinity.inventory.AdmissionMetadata;
import org.sinytra.connector.infinity.inventory.AdmissionInventory.SourceChain;
import java.io.*;
import java.nio.file.*;

/** Host I/O adapter; parsing and the canonical model are owned by the single BOOT component. */
public final class AdmissionMetadataScanner {
    private AdmissionMetadataScanner() {}
    public static AdmissionMetadata.Scan scan(Path path, SourceChain source) throws IOException {
        return AdmissionMetadata.scan(path, source);
    }
    public static AdmissionMetadata.Scan scan(JarContents contents, SourceChain source) throws IOException {
        return AdmissionMetadata.scan(contents.getPrimaryPath(), source, new AdmissionMetadata.Resources() {
            public boolean has(String resource) { return contents.findFile(resource).isPresent(); }
            public InputStream open(String resource) throws IOException {
                Path path = Path.of(contents.findFile(resource).orElseThrow(() -> new IOException("Missing descriptor " + resource)));
                return Files.newInputStream(path);
            }
        });
    }
}
