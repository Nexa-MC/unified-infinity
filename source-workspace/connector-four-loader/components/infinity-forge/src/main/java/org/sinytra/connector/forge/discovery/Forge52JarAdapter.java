package org.sinytra.connector.forge.discovery;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.jar.Manifest;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipOutputStream;
import org.sinytra.connector.forge.transform.Forge52Symbols;
import org.sinytra.connector.infinity.BuildIdentity;

/** Static admission: transforms bytes only; never loads candidate classes. */
public final class Forge52JarAdapter {
    public static final String SOURCE_TOML = "META-INF/mods.toml";
    public static final String TARGET_TOML = "META-INF/neoforge.mods.toml";
    public static final String AUDIT_RESOURCE = "META-INF/unified-infinity/forge52-audit.json";
    public static final String TARGET = "minecraft=1.21.1;neoforge=21.1.219;fml=4.0.42;bus=8.0.5;forge=52.1.0;namespace=Mojmap";
    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().disableHtmlEscaping().create();
    private static final int MAX_ENTRIES = 50_000;
    private static final int MAX_ENTRY = 32 * 1024 * 1024;
    private static final int MAX_CLASS = 8 * 1024 * 1024;
    private static final int MAX_METADATA = 1024 * 1024;
    private static final long MAX_TOTAL = 256L * 1024 * 1024;
    private Forge52JarAdapter() {}

    public record Result(Path output, String inputSha256, String outputSha256, boolean cacheHit) {}

    public static Result adapt(Path input, Path cache, String side) throws IOException {
        if (!Files.isRegularFile(input)) throw Forge52Symbols.unsupported("only regular JAR candidates are supported: " + input);
        String inputHash = sha256(input);
        String rulesHash = sha256(Forge52Symbols.rules().getBytes(StandardCharsets.UTF_8));
        String identity = inputHash + "\n" + TARGET + "\n" + side + "\n" + rulesHash + "\n"
            + BuildIdentity.SOURCE_SHA256 + "\n" + BuildIdentity.TRANSFORM_CACHE_SUFFIX;
        String key = sha256(identity.getBytes(StandardCharsets.UTF_8));
        Files.createDirectories(cache);
        Path output = cache.resolve(key + ".jar");
        Path receipt = cache.resolve(key + ".sha256");
        // Always validate an existing output's actual bytes. A half commit, missing
        // receipt or corruption is not a cache hit and cannot admit a stale jar.
        if (Files.isRegularFile(output) && Files.isRegularFile(receipt)) {
            String actual = sha256(output);
            if (Files.readString(receipt).trim().equals(actual)) return new Result(output, inputHash, actual, true);
        }
        Map<String, byte[]> entries = readBounded(input);
        requireSupportedResources(entries);
        String originalToml = new String(entries.get(SOURCE_TOML), StandardCharsets.UTF_8);
        Forge52Resources.Plan resources = Forge52Resources.inspect(entries);
        Forge52Metadata.Projection metadata = Forge52Metadata.project(originalToml, side, resources);
        Set<String> symbols = new TreeSet<>();
        Map<String, String> hierarchy = new LinkedHashMap<>();
        entries.forEach((name, bytes) -> {
            if (name.endsWith(".class")) {
                var reader = new org.objectweb.asm.ClassReader(bytes);
                hierarchy.put(reader.getClassName(), reader.getSuperName());
            }
        });
        Set<String> eventSubclasses = new java.util.HashSet<>();
        hierarchy.keySet().forEach(name -> {
            String current = name;
            Set<String> visited = new java.util.HashSet<>();
            while (current != null && visited.add(current)) {
                current = hierarchy.get(current);
                if ("net/minecraftforge/eventbus/api/Event".equals(current)) { eventSubclasses.add(name); break; }
            }
        });
        for (Map.Entry<String, byte[]> entry : entries.entrySet()) {
            if (entry.getKey().endsWith(".class")) {
                try { entry.setValue(Forge52Symbols.transform(entry.getValue(), symbols, eventSubclasses)); }
                catch (RuntimeException e) { throw new IOException("Forge candidate " + input.getFileName() + " class " + entry.getKey() + ": " + e.getMessage(), e); }
            }
        }
        Map<String, Object> audit = new LinkedHashMap<>();
        audit.put("adapterAbi", Forge52Symbols.ABI); audit.put("target", TARGET);
        audit.put("originalSha256", inputHash); audit.put("sourceBuildSha256", BuildIdentity.SOURCE_SHA256);
        audit.put("transformCacheSuffix", BuildIdentity.TRANSFORM_CACHE_SUFFIX); audit.put("rulesSha256", rulesHash);
        audit.put("originalMetadataResource", SOURCE_TOML); audit.put("effectiveMetadataResource", TARGET_TOML);
        audit.put("metadata", metadata.audit()); audit.put("symbolPlan", symbols); audit.put("resources", resources.audit());
        audit.put("ownership", "native FML admission, game module layer, host event bus, host registry and Mixin engine");
        entries.put(TARGET_TOML, metadata.toml().getBytes(StandardCharsets.UTF_8));
        entries.put(AUDIT_RESOURCE, GSON.toJson(audit).getBytes(StandardCharsets.UTF_8));
        Path temporary = Files.createTempFile(cache, key + ".", ".pending");
        Path receiptTemporary = null;
        try {
            try (ZipOutputStream stream = new ZipOutputStream(Files.newOutputStream(temporary))) {
                for (var entry : entries.entrySet()) {
                    ZipEntry zipEntry = new ZipEntry(entry.getKey()); zipEntry.setTime(0L);
                    stream.putNextEntry(zipEntry); stream.write(entry.getValue()); stream.closeEntry();
                }
            }
            String outputHash = sha256(temporary);
            if (!sha256(input).equals(inputHash)) throw new IOException("Forge input changed during adaptation: " + input);
            receiptTemporary = Files.createTempFile(cache, key + ".", ".digest.pending");
            Files.writeString(receiptTemporary, outputHash + "\n");
            atomicMove(temporary, output);
            atomicMove(receiptTemporary, receipt);
            return new Result(output, inputHash, outputHash, false);
        } finally {
            Files.deleteIfExists(temporary);
            if (receiptTemporary != null) Files.deleteIfExists(receiptTemporary);
        }
    }

    private static Map<String, byte[]> readBounded(Path input) throws IOException {
        Map<String, byte[]> contents = new TreeMap<>();
        Set<String> allPaths = new java.util.HashSet<>();
        long total = 0;
        try (ZipFile zip = new ZipFile(input.toFile())) {
            var entries = zip.entries();
            while (entries.hasMoreElements()) {
                ZipEntry entry = entries.nextElement();
                String name = entry.getName();
                if (!allPaths.add(name)) throw new IOException("Duplicate Forge JAR entry " + name);
                if (allPaths.size() > MAX_ENTRIES) throw new IOException("Forge JAR entry limit exceeded");
                validatePath(name);
                if (entry.isDirectory()) continue;
                int limit = name.endsWith(".class") ? MAX_CLASS : name.equals(SOURCE_TOML) ? MAX_METADATA : MAX_ENTRY;
                if (entry.getSize() > limit) throw new IOException("Forge JAR entry exceeds bound: " + name);
                byte[] bytes;
                try (var stream = zip.getInputStream(entry)) { bytes = stream.readNBytes(limit + 1); }
                if (bytes.length > limit) throw new IOException("Forge JAR entry exceeds bound: " + name);
                total += bytes.length;
                if (total > MAX_TOTAL) throw new IOException("Forge JAR total uncompressed bound exceeded");
                contents.put(name, bytes);
            }
        }
        return contents;
    }

    private static void validatePath(String name) throws IOException {
        if (name.isEmpty() || name.startsWith("/") || name.contains("\\") || name.indexOf('\0') >= 0
            || name.matches("^[A-Za-z]:.*")) throw new IOException("Unsafe Forge JAR path: " + name);
        for (String segment : name.split("/", -1))
            if (segment.equals(".") || segment.equals("..")) throw new IOException("Unsafe Forge JAR path: " + name);
        if (name.contains("//")) throw new IOException("Noncanonical Forge JAR path: " + name);
    }

    private static void requireSupportedResources(Map<String, byte[]> entries) throws IOException {
        if (!entries.containsKey(SOURCE_TOML)) throw new IOException("Missing genuine Forge " + SOURCE_TOML);
        for (String alternate : Set.of(TARGET_TOML, "fabric.mod.json", "quilt.mod.json"))
            if (entries.containsKey(alternate)) throw Forge52Symbols.unsupported("ambiguous dual descriptor " + alternate);
        for (String name : entries.keySet()) {
            String upper = name.toUpperCase(java.util.Locale.ROOT);
            if (name.equals("module-info.class") || name.startsWith("META-INF/versions/")
                || name.startsWith("META-INF/jarjar/") || name.equals("META-INF/coremods.json")
                || name.equals("META-INF/accesstransformer.cfg") || name.equals(AUDIT_RESOURCE)
                || upper.startsWith("META-INF/") && (upper.endsWith(".SF") || upper.endsWith(".RSA") || upper.endsWith(".DSA") || upper.endsWith(".EC")))
                throw Forge52Symbols.unsupported("resource " + name);
            if (name.endsWith(".jar")) throw Forge52Symbols.unsupported("nested JAR " + name);
        }
        byte[] bytes = entries.get("META-INF/MANIFEST.MF");
        if (bytes != null) {
            Manifest manifest = new Manifest(new ByteArrayInputStream(bytes));
            for (String field : Set.of("FMLAT", "FMLCorePlugin", "TweakClass", "ContainedDeps"))
                if (manifest.getMainAttributes().getValue(field) != null) throw Forge52Symbols.unsupported("manifest " + field);
            String type = manifest.getMainAttributes().getValue("FMLModType");
            if (type != null && !type.equals("MOD")) throw Forge52Symbols.unsupported("FMLModType=" + type);
        }
    }

    private static void atomicMove(Path from, Path to) throws IOException {
        try { Files.move(from, to, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING); }
        catch (AtomicMoveNotSupportedException e) { throw new IOException("Forge cache requires atomic commit on " + to.getParent(), e); }
    }

    public static String sha256(Path path) throws IOException {
        MessageDigest digest = digest();
        try (var input = Files.newInputStream(path)) {
            byte[] buffer = new byte[64 * 1024]; int size;
            while ((size = input.read(buffer)) != -1) digest.update(buffer, 0, size);
        }
        return HexFormat.of().formatHex(digest.digest());
    }
    private static String sha256(byte[] bytes) { return HexFormat.of().formatHex(digest().digest(bytes)); }
    private static MessageDigest digest() {
        try { return MessageDigest.getInstance("SHA-256"); }
        catch (NoSuchAlgorithmException e) { throw new AssertionError(e); }
    }
}
