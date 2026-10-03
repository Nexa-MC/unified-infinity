package org.sinytra.connector.locator;

import com.google.gson.*;
import cpw.mods.jarhandling.SecureJar;
import net.neoforged.fml.loading.FMLPaths;
import net.neoforged.neoforgespi.locating.IModFile;
import org.sinytra.connector.transformer.quilt.NativeQuiltSources;
import java.io.*;
import java.lang.reflect.Proxy;
import java.nio.file.*;
import java.util.*;
import java.util.jar.*;

public final class ManagedQslTest {
    private static int checks;
    private static void check(boolean value, String label) { checks++; if (!value) throw new AssertionError(label); }
    public static void main(String[] args) throws Exception {
        Path temp = Files.createTempDirectory("managed-qsl-intake-"); FMLPaths.loadAbsolutePaths(temp);
        Path host = Path.of(args[0]).toAbsolutePath();
        IModFile view = view(host);
        List<Path> selected = ManagedQuiltModules.discover(List.of(view));
        check(selected.size() == 2, "two managed modules selected");
        for (Path path : selected) {
            check(Files.isRegularFile(path), "exact original bytes materialized");
            check(NativeQuiltSources.chain(path.toString()).get(0).equals(host), "outer host provenance");
            check(!NativeQuiltSources.chain(path.toString()).get(1).isAbsolute(), "nested relative provenance");
            try (JarFile original = new JarFile(path.toFile())) {
                var metadata = org.sinytra.connector.transformer.quilt.NativeQuiltMetadata.parse(original.getInputStream(original.getJarEntry("quilt.mod.json")), path.toString(),
                    new net.fabricmc.loader.impl.metadata.VersionOverrides(), new net.fabricmc.loader.impl.metadata.DependencyOverrides(temp), true);
                var fml = new net.neoforged.fml.loading.moddiscovery.ModFile(SecureJar.from(path),
                    file -> FabricModMetadataParser.createForgeMetadata(file, new ConnectorFabricModMetadata(metadata), List.of(), false),
                    net.neoforged.neoforgespi.locating.ModFileDiscoveryAttributes.DEFAULT);
                check(fml.identifyMods(), "native metadata final FML identification");
                var version = fml.getModInfos().get(0).getVersion();
                check(version.toString().equals("10.0.0-alpha.5+1.21.1"), "raw native FML version preserved");
                check(org.apache.maven.artifact.versioning.VersionRange.createFromVersionSpec("[10.0.0-alpha.5+1.21.1]").containsVersion(version), "exact host QSL dependency matches final FML version");
            }
        }
        check(ManagedQuiltModules.discover(List.of(view)).equals(selected), "warm extraction stable");
        byte[] before = Files.readAllBytes(selected.get(0));
        Files.writeString(selected.get(0), "own test simulates stale corrupted cache");
        ManagedQuiltModules.discover(List.of(view));
        check(Arrays.equals(before, Files.readAllBytes(selected.get(0))), "corrupt payload cache repaired from verified source");
        for (String mode : List.of("bad-hash", "bad-path", "duplicate", "missing", "bad-payload")) {
            Path broken = temp.resolve(mode + ".jar");
            try (JarFile input = new JarFile(host.toFile()); JarOutputStream out = new JarOutputStream(Files.newOutputStream(broken))) {
                for (var it = input.entries(); it.hasMoreElements();) {
                    JarEntry entry = it.nextElement(); if (!entry.getName().equals(ManagedQuiltModules.INVENTORY) && !entry.getName().startsWith("META-INF/jarjar/qsl_base-") && !entry.getName().startsWith("META-INF/jarjar/lifecycle_events-")) continue;
                    byte[] bytes = input.getInputStream(entry).readAllBytes();
                    if (entry.getName().equals(ManagedQuiltModules.INVENTORY)) {
                        JsonObject record = JsonParser.parseString(new String(bytes, java.nio.charset.StandardCharsets.UTF_8)).getAsJsonObject(); JsonArray modules = record.getAsJsonArray("modules");
                        switch (mode) {
                            case "bad-hash" -> modules.get(0).getAsJsonObject().addProperty("sha256", "0".repeat(64));
                            case "bad-path" -> modules.get(0).getAsJsonObject().addProperty("path", "../escape.jar");
                            case "duplicate" -> modules.set(1, modules.get(0).deepCopy());
                            case "missing" -> modules.remove(1);
                        }
                        bytes = record.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8);
                    } else if (mode.equals("bad-payload")) bytes = new byte[] {1,2,3};
                    out.putNextEntry(new JarEntry(entry.getName())); out.write(bytes); out.closeEntry();
                }
            }
            try { ManagedQuiltModules.discover(List.of(view(broken))); throw new AssertionError("accepted " + mode); }
            catch (IOException | IllegalArgumentException expected) { check(true, "reject " + mode); }
        }
        System.out.println("MANAGED_QSL_INTAKE " + checks + " assertions PASS");
    }
    private static IModFile view(Path path) {
        SecureJar jar = SecureJar.from(path);
        return (IModFile) Proxy.newProxyInstance(ManagedQslTest.class.getClassLoader(), new Class<?>[]{IModFile.class}, (proxy, method, args) -> {
            if (method.getName().equals("getSecureJar")) return jar;
            if (method.getName().equals("toString")) return path.toString();
            throw new UnsupportedOperationException(method.getName());
        });
    }
}
