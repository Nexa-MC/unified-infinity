package org.sinytra.connector.infinity.inventory;

import com.electronwill.nightconfig.core.UnmodifiableConfig;
import com.electronwill.nightconfig.toml.TomlParser;
import com.google.gson.*;
import org.sinytra.connector.infinity.inventory.AdmissionInventory.*;
import org.sinytra.connector.infinity.inventory.InfrastructurePolicy;

import java.io.*;
import java.lang.module.ModuleDescriptor;
import java.util.jar.Manifest;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.jar.JarFile;
import java.util.zip.ZipEntry;

/** Bounded descriptor-only scan. No class loading, mixin parsing, transformer or archive rewriting. */
public final class AdmissionMetadata {
    private static final int MAX_DESCRIPTOR = 1024 * 1024;
    private static final Set<String> EARLY_SERVICES = Set.of(
        "cpw.mods.modlauncher.api.ITransformationService",
        "net.neoforged.neoforgespi.locating.IModFileCandidateLocator",
        "net.neoforged.neoforgespi.locating.IModFileReader",
        "net.neoforged.neoforgespi.locating.IDependencyLocator",
        "net.neoforged.neoforgespi.earlywindow.GraphicsBootstrapper",
        "net.neoforged.neoforgespi.earlywindow.ImmediateWindowProvider");
    public record Mod(String id, String name, Optional<String> declaredVersion, List<String> licenses) {
        public Mod { licenses = List.copyOf(licenses); }
        public Mod(String id, String name, Optional<String> declaredVersion) { this(id, name, declaredVersion, List.of()); }
    }
    public record Scan(InfrastructurePolicy.Candidate candidate, List<Mod> mods, List<String> declaredNestedJars) {
        public Scan { mods = List.copyOf(mods); declaredNestedJars = List.copyOf(declaredNestedJars); }
    }
    private AdmissionMetadata() {}
    public static Scan scan(Path path, SourceChain source) throws IOException {
        try (JarFile jar = new JarFile(path.toFile())) {
            return scan(path, source, new Resources() {
                public boolean has(String resource) { return jar.getEntry(resource) != null; }
                public InputStream open(String resource) throws IOException {
                    ZipEntry entry = jar.getEntry(resource);
                    if (entry == null || entry.getSize() > MAX_DESCRIPTOR) throw new IOException("Missing or oversized descriptor " + resource);
                    return jar.getInputStream(entry);
                }
            });
        }
    }
    public static Scan scan(Path path, SourceChain source, Resources jar) throws IOException {
        try {
            boolean services = EARLY_SERVICES.stream().anyMatch(s -> jar.has("META-INF/services/" + s));
            // Read module metadata, never initialize provider classes. Multi-release selection follows the running JDK.
            String moduleInfo = jar.has("module-info.class") ? "module-info.class" : null;
            boolean multiRelease = jar.has("META-INF/MANIFEST.MF") && Boolean.parseBoolean(
                new Manifest(new ByteArrayInputStream(readBytes(jar, "META-INF/MANIFEST.MF"))).getMainAttributes().getValue("Multi-Release"));
            if (multiRelease) for (int version = Runtime.version().feature(); version >= 9; version--) {
                String candidate = "META-INF/versions/" + version + "/module-info.class";
                if (jar.has(candidate)) { moduleInfo = candidate; break; }
            }
            if (moduleInfo != null) {
                ModuleDescriptor descriptor = ModuleDescriptor.read(new ByteArrayInputStream(readBytes(jar, moduleInfo)));
                services |= descriptor.provides().stream().anyMatch(provider -> EARLY_SERVICES.contains(provider.service()));
            }
            boolean neo = jar.has("META-INF/neoforge.mods.toml");
            boolean forge = jar.has("META-INF/mods.toml");
            boolean quilt = jar.has("quilt.mod.json");
            boolean fabric = jar.has("fabric.mod.json");
            UnmodifiableConfig nativeConfig = neo || forge ? new TomlParser().parse(read(jar,
                neo ? "META-INF/neoforge.mods.toml" : "META-INF/mods.toml")) : null;
            if (neo && fabric && nativeConfig.<UnmodifiableConfig>getOptional("properties")
                    .map(properties -> properties.contains("connector:placeholder")).orElse(false)) neo = false;
            Ecosystem ecosystem; List<Mod> mods = new ArrayList<>(); List<String> nested = new ArrayList<>();
            if (neo || forge) {
                ecosystem = neo ? Ecosystem.NEOFORGE : Ecosystem.FORGE;
                UnmodifiableConfig config = nativeConfig;
                List<? extends UnmodifiableConfig> declarations = config.get("mods");
                if (declarations != null) for (UnmodifiableConfig mod : declarations) {
                    String id = mod.get("modId");
                    if (id == null) continue;
                    mods.add(new Mod(id, mod.<String>getOptional("displayName").orElse(id), mod.<Object>getOptional("version").map(Object::toString), declaredLicenses(config)));
                }
            } else if (quilt || fabric) {
                ecosystem = quilt ? Ecosystem.QUILT : Ecosystem.FABRIC;
                JsonObject json = JsonParser.parseString(read(jar, quilt ? "quilt.mod.json" : "fabric.mod.json")).getAsJsonObject();
                JsonObject loader = quilt ? json.getAsJsonObject("quilt_loader") : json;
                String id = loader.get("id").getAsString();
                JsonObject presentation = quilt && loader.has("metadata") ? loader.getAsJsonObject("metadata") : loader;
                mods.add(new Mod(id, presentation.has("name") ? presentation.get("name").getAsString() : id,
                    loader.has("version") ? Optional.of(loader.get("version").getAsString()) : Optional.empty(), declaredLicenses(presentation)));
                if (loader.has("jars")) for (JsonElement entry : loader.getAsJsonArray("jars"))
                    nested.add(entry.isJsonPrimitive() ? entry.getAsString() : entry.getAsJsonObject().get("file").getAsString());
            } else ecosystem = Ecosystem.UNKNOWN;
            if (jar.has("META-INF/jarjar/metadata.json")) {
                JsonObject jarjar = JsonParser.parseString(read(jar, "META-INF/jarjar/metadata.json")).getAsJsonObject();
                if (jarjar.has("jars")) for (JsonElement entry : jarjar.getAsJsonArray("jars"))
                    nested.add(entry.getAsJsonObject().get("path").getAsString());
            }
            if (jar.has("META-INF/unified-infinity/bundled-qsl.json") && TrustedPayloads.root(path).isPresent()) {
                JsonObject managed = JsonParser.parseString(read(jar, "META-INF/unified-infinity/bundled-qsl.json")).getAsJsonObject();
                if (managed.has("modules")) for (JsonElement entry : managed.getAsJsonArray("modules"))
                    nested.add(entry.getAsJsonObject().get("path").getAsString());
            }
            for (String entry : nested) source.nested(entry); // validate archive paths even before extraction
            return new Scan(new InfrastructurePolicy.Candidate(path, source, ecosystem, mods.stream().map(Mod::id).toList(), services), mods, nested);
        } catch (RuntimeException e) { throw new IOException("Invalid admission descriptor in " + path + ": " + e.getMessage(), e); }
    }
    private static List<String> declaredLicenses(UnmodifiableConfig config) {
        Optional<Object> declared = config.getOptional("license");
        if (declared.isEmpty()) return List.of();
        if (!(declared.get() instanceof String value)) throw new IllegalArgumentException("Native license declaration must be a string");
        return value.isBlank() ? List.of() : List.of(value);
    }
    private static List<String> declaredLicenses(JsonObject metadata) {
        if (!metadata.has("license") || metadata.get("license").isJsonNull()) return List.of();
        JsonElement declared = metadata.get("license");
        List<String> result = new ArrayList<>();
        for (JsonElement entry : declared.isJsonArray() ? declared.getAsJsonArray() : List.of(declared)) {
            if (!entry.isJsonPrimitive() || !entry.getAsJsonPrimitive().isString())
                throw new IllegalArgumentException("License declaration must contain strings");
            String value = entry.getAsString();
            if (!value.isBlank()) result.add(value);
        }
        return List.copyOf(result);
    }
    public interface Resources { boolean has(String resource); InputStream open(String resource) throws IOException; }
    private static String read(Resources jar, String resource) throws IOException {
        return new String(readBytes(jar, resource), StandardCharsets.UTF_8);
    }
    private static byte[] readBytes(Resources jar, String resource) throws IOException {
        try (InputStream stream = jar.open(resource)) {
            byte[] bytes = stream.readNBytes(MAX_DESCRIPTOR + 1);
            if (bytes.length > MAX_DESCRIPTOR) throw new IOException("Oversized descriptor " + resource);
            return bytes;
        }
    }
}
