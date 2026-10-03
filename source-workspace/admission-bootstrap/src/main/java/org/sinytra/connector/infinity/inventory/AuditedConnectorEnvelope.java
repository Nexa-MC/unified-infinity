package org.sinytra.connector.infinity.inventory;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.*;
import java.util.zip.ZipFile;

/** Exact audited official release exclusion, never a trust grant or generic envelope classifier. */
final class AuditedConnectorEnvelope {
    static final String OUTER_SHA256 = "270b2d385be50932419b7d57d4f4bf7328d70e08d0dd9d88adefdb3c5d08a986";
    private static final String RUNTIME = "META-INF/jarjar/runtime-1.0.0+1.21.1.jar";
    private static final String CONNECTOR = "META-INF/jarjar/org.sinytra.connector-2.0.0-beta.17+1.21.1-mod.jar";
    private static final Map<String, String> CHILDREN = Map.of(
        RUNTIME, "36de91a417138f01a1801b7e2ae59bb1052c8ddb23b1352d3fe952b3d33a5e06",
        CONNECTOR, "0bd1b42d10a78152287935b02b06554478e4f38fad3e5fce334a9e7efc920266");
    private static final Map<String, String> SERVICES = Map.of(
        "cpw.mods.modlauncher.api.ITransformationService", "org.sinytra.connector.service.ConnectorLoaderService",
        "net.neoforged.neoforgespi.coremod.ICoreMod", "org.sinytra.connector.ConnectorCoremods",
        "net.neoforged.neoforgespi.locating.IDependencyLocator", "org.sinytra.connector.locator.ConnectorLocator",
        "net.neoforged.neoforgespi.locating.IModFileCandidateLocator", "org.sinytra.connector.locator.ConnectorEarlyLocatorBootstrap");
    record Nested(String entry, String sha256, List<String> primaryIds, boolean earlyServiceProvider) {
        Nested { primaryIds = List.copyOf(primaryIds); }
    }
    private AuditedConnectorEnvelope() {}

    /** Uses the already-frozen canonical descriptor/child scan. Resource hashes pin audited release metadata. */
    static boolean matches(String verifiedOuterSha256, AdmissionMetadata.Scan scan, ZipFile zip, List<Nested> children) throws IOException {
        if (!OUTER_SHA256.equals(verifiedOuterSha256) || !scan.candidate().primaryIds().isEmpty()
            || !scan.candidate().earlyServiceProvider() || !Set.copyOf(scan.declaredNestedJars()).equals(CHILDREN.keySet())
            || scan.declaredNestedJars().size() != 2 || children.size() != 2) return false;
        var foundChildren = new HashSet<String>();
        for (Nested child : children) {
            if (!foundChildren.add(child.entry()) || !Objects.equals(CHILDREN.get(child.entry()), child.sha256())
                || child.earlyServiceProvider() || !child.primaryIds().equals(child.entry().equals(CONNECTOR) ? List.of("connector") : List.of())) return false;
        }
        Set<String> jars = new HashSet<>(), providers = new HashSet<>();
        for (var entries = zip.entries(); entries.hasMoreElements();) {
            var entry = entries.nextElement(); String name = entry.getName();
            if (entry.isDirectory()) continue;
            if (name.equals("fabric.mod.json") || name.equals("quilt.mod.json") || name.equals("META-INF/neoforge.mods.toml")
                || name.equals("META-INF/mods.toml") || name.equals("module-info.class") || name.endsWith("/module-info.class")) return false;
            if (name.toLowerCase(Locale.ROOT).endsWith(".jar")) jars.add(name);
            if (name.startsWith("META-INF/services/")) providers.add(name.substring("META-INF/services/".length()));
        }
        if (!jars.equals(CHILDREN.keySet()) || !providers.equals(SERVICES.keySet())) return false;
        // Exact manifest bytes pin release version, module name and attribution; JarJar bytes pin coordinates/ranges.
        if (!digest(read(zip, "META-INF/MANIFEST.MF", 4096)).equals("8f7f724e8cdc23bd2f9d5e895cb14ed7a802e666aa5c1dd3b8fa83f0e7816ce7")
            || !digest(read(zip, "META-INF/jarjar/metadata.json", 8192)).equals("410d481de679fff772d713c21912f8fd3e7c121328a3723465bca4d971a44d93")) return false;
        for (var service : SERVICES.entrySet()) {
            String text = new String(read(zip, "META-INF/services/" + service.getKey(), 8192), StandardCharsets.UTF_8);
            List<String> names = text.lines().map(line -> line.split("#", 2)[0].trim()).filter(line -> !line.isEmpty()).toList();
            if (!names.equals(List.of(service.getValue()))) return false;
        }
        return true;
    }
    private static byte[] read(ZipFile zip, String name, int limit) throws IOException {
        var entry = zip.getEntry(name);
        if (entry == null || entry.isDirectory() || entry.getSize() > limit) throw new IOException("Audited envelope resource missing or oversized");
        try (var input = zip.getInputStream(entry)) {
            byte[] bytes = input.readNBytes(limit + 1);
            if (bytes.length > limit) throw new IOException("Audited envelope resource exceeds bound");
            return bytes;
        }
    }
    private static String digest(byte[] bytes) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)); }
        catch (NoSuchAlgorithmException impossible) { throw new AssertionError(impossible); }
    }
}
