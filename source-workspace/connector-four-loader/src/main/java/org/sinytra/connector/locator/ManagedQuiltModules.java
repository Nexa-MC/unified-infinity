package org.sinytra.connector.locator;

import com.google.gson.*;
import net.neoforged.neoforgespi.locating.IModFile;
import org.sinytra.connector.transformer.quilt.NativeQuiltSources;
import org.sinytra.connector.util.ConnectorUtil;
import org.sinytra.connector.infinity.inventory.TrustedPayloads;
import org.sinytra.connector.infinity.inventory.AdmissionSession;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.*;
import java.util.*;

/** Extract only the two exact host-owned QSL payloads into the ordinary candidate pipeline.
 * Standard NeoForge JarJar discovery must not independently admit these native Quilt payloads.
 */
final class ManagedQuiltModules {
    static final String INVENTORY = "META-INF/unified-infinity/bundled-qsl.json";
    private static final String VERSION = "10.0.0-alpha.5+1.21.1";
    private static final Map<String, String> PINS = Map.of(
        "quilt_base", "7eb4ec613f901ef7232f9f84ee91be5576f00682f32ad9c9f7b1a679bcf82465",
        "quilt_lifecycle_events", "1a1f9b72c38e2475b471df1dcff7992d6ae4955e8a2cd8288bb3ba3986768aa4");
    private ManagedQuiltModules() {}

    static List<Path> discover(List<IModFile> hosts) throws IOException {
        List<Path> result = new ArrayList<>(); Set<String> seen = new HashSet<>();
        for (IModFile host : hosts) {
            Path inventory = host.getSecureJar().getPath(INVENTORY);
            if (!Files.isRegularFile(inventory)) continue;
            TrustedPayloads.root(host.getSecureJar().getPrimaryPath())
                .orElseThrow(() -> new IOException("Managed QSL requires a bootstrap-verified host root; external inventories cannot grant trust: " + host.getFilePath()));
            JsonObject record;
            try (InputStream input = Files.newInputStream(inventory)) {
                byte[] bytes = input.readNBytes(65537);
                if (bytes.length > 65536) throw new IOException("Managed QSL inventory exceeds 64 KiB");
                record = JsonParser.parseString(new String(bytes, StandardCharsets.UTF_8)).getAsJsonObject();
            }
            JsonArray modules = record.getAsJsonArray("modules");
            if (modules == null || (modules.size() != 0 && modules.size() != 2)) throw new IOException("Managed QSL profile requires exactly base and lifecycle");
            for (JsonElement entry : modules) {
                JsonObject module = entry.getAsJsonObject(); String id = module.get("id").getAsString();
                String expected = PINS.get(id);
                if (expected == null || !seen.add(id)) throw new IOException("Unknown or duplicate managed QSL module " + id);
                if (!expected.equals(module.get("sha256").getAsString()) || !VERSION.equals(module.get("version").getAsString()))
                    throw new IOException("Managed QSL pin mismatch for " + id);
                String artifact = id.equals("quilt_base") ? "qsl_base" : "lifecycle_events";
                String path = "META-INF/jarjar/" + artifact + "-" + VERSION + ".jar";
                if (!path.equals(module.get("path").getAsString())) throw new IOException("Unexpected managed QSL payload path for " + id);
                byte[] bytes;
                try (InputStream in = Files.newInputStream(host.getSecureJar().getPath(path))) {
                    bytes = in.readNBytes(8 * 1024 * 1024 + 1);
                    if (bytes.length > 8 * 1024 * 1024) throw new IOException("Oversized managed QSL payload " + id);
                }
                if (!digest(bytes).equals(expected)) throw new IOException("Managed QSL payload digest mismatch for " + id);
                Path target = AdmissionSession.current().nestedArchive(host.getSecureJar().getPrimaryPath(), path)
                    .orElseThrow(() -> new IOException("Managed QSL payload was not admitted by the launch session: " + id));
                if (TrustedPayloads.find(target, Set.of(id)).isEmpty())
                    throw new IOException("Managed QSL lacks its pinned launch receipt: " + id);
                NativeQuiltSources.record(target, List.of(host.getSecureJar().getPrimaryPath().toAbsolutePath().normalize(), Path.of(path)));
                result.add(target);
            }
        }
        return List.copyOf(result);
    }
    private static String digest(byte[] bytes) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)); }
        catch (NoSuchAlgorithmException e) { throw new AssertionError(e); }
    }
}
