package org.sinytra.connector.infinity.inventory;

import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.zip.*;
import static org.sinytra.connector.infinity.inventory.AdmissionInventory.*;

/** Exercises original archive descriptors, not a host parser's presentation fallback. */
public final class AdmissionMetadataLicenseTest {
    private static int assertions;
    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("admission-original-license-");
        try {
            check(scan(directory, "fabric-absent", "fabric.mod.json", "{\"schemaVersion\":1,\"id\":\"fixture\",\"version\":\"1+raw\"}").licenses().isEmpty(), "Absent Fabric license stays unknown");
            check(scan(directory, "fabric-explicit", "fabric.mod.json", "{\"schemaVersion\":1,\"id\":\"fixture\",\"version\":\"1+raw\",\"license\":[\"MIT\",\"Apache-2.0\"]}").licenses().equals(List.of("MIT", "Apache-2.0")), "Original Fabric license list/order preserved");
            check(scan(directory, "fabric-rights", "fabric.mod.json", "{\"schemaVersion\":1,\"id\":\"fixture\",\"version\":\"1\",\"license\":\"All Rights Reserved\"}").licenses().equals(List.of("All Rights Reserved")), "Explicit reserved-rights declaration remains a fact");
            check(scan(directory, "quilt-absent", "quilt.mod.json", "{\"schema_version\":1,\"quilt_loader\":{\"id\":\"fixture\",\"version\":\"1\",\"metadata\":{\"name\":\"Fixture\"}}}").licenses().isEmpty(), "Absent Quilt license stays unknown");
            check(scan(directory, "quilt-explicit", "quilt.mod.json", "{\"schema_version\":1,\"quilt_loader\":{\"id\":\"fixture\",\"version\":\"1\",\"metadata\":{\"name\":\"Fixture\",\"license\":\"Apache-2.0\"}}}").licenses().equals(List.of("Apache-2.0")), "Quilt metadata license retained");
            String nativeDescriptor = "modLoader=\"javafml\"\nloaderVersion=\"[1,)\"\n%s\n[[mods]]\nmodId=\"fixture\"\nversion=\"${file.jarVersion}\"\n";
            for (String descriptor : List.of("META-INF/mods.toml", "META-INF/neoforge.mods.toml")) {
                String lane = descriptor.contains("neoforge") ? "neo" : "forge";
                check(scan(directory, lane + "-absent", descriptor, nativeDescriptor.formatted("")).licenses().isEmpty(), "Absent " + lane + " license stays unknown");
                var explicit = scan(directory, lane + "-explicit", descriptor, nativeDescriptor.formatted("license=\"MIT OR Apache-2.0\""));
                check(explicit.licenses().equals(List.of("MIT OR Apache-2.0")), "Original " + lane + " SPDX expression unchanged");
                check(explicit.declaredVersion().orElseThrow().equals("${file.jarVersion}"), "Declared version expression unchanged");
                try { explicit.licenses().clear(); throw new AssertionError("Mutable license record"); }
                catch (UnsupportedOperationException expected) { assertions++; }
            }
            System.out.println("PASS " + assertions + " original-descriptor license assertions");
        } finally {
            try (var paths = Files.walk(directory)) {
                for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) Files.delete(path);
            }
        }
    }
    private static AdmissionMetadata.Mod scan(Path directory, String name, String descriptor, String text) throws Exception {
        Path file = directory.resolve(name + ".jar");
        try (ZipOutputStream output = new ZipOutputStream(Files.newOutputStream(file))) {
            output.putNextEntry(new ZipEntry(descriptor)); output.write(text.getBytes(StandardCharsets.UTF_8)); output.closeEntry();
        }
        return AdmissionMetadata.scan(file, new SourceChain(file.toString(), List.of())).mods().getFirst();
    }
    private static void check(boolean condition, String message) { assertions++; if (!condition) throw new AssertionError(message); }
}
