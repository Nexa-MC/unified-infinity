package org.sinytra.connector.transformer.quilt;

import com.google.gson.*;
import com.google.gson.stream.JsonReader;
import com.google.gson.stream.JsonToken;
import net.fabricmc.loader.impl.metadata.*;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Strict, deliberately bounded native Quilt -> existing candidate graph projection.
 * The source archive is never rewritten. The complete native document remains authoritative.
 */
public final class NativeQuiltMetadata {
    public static final String FILE = "quilt.mod.json";
    public static final String RAW_KEY = "infinity:quilt_metadata";
    public static final String PROFILE = "native-quilt-v1";
    private static final Set<String> LOADER_KEYS = Set.of("group", "id", "version", "metadata", "entrypoints", "language_adapters", "jars", "depends", "breaks", "provides", "load_type", "intermediate_mappings");
    private NativeQuiltMetadata() {}

    public static LoaderModMetadata parse(InputStream input, String source, VersionOverrides versions,
                                           DependencyOverrides dependencies, boolean managedQsl) throws IOException, ParseMetadataException {
        byte[] bytes = input.readNBytes(1024 * 1024 + 1);
        if (bytes.length > 1024 * 1024) throw fail(source, "metadata exceeds 1 MiB");
        JsonObject root;
        try (JsonReader reader = new JsonReader(new InputStreamReader(new ByteArrayInputStream(bytes), StandardCharsets.UTF_8))) {
            reader.setLenient(false);
            root = object(readStrict(reader, 0), source, "root");
            if (reader.peek() != JsonToken.END_DOCUMENT) throw fail(source, "trailing JSON data");
        } catch (IOException | RuntimeException e) {
            throw fail(source, "invalid JSON: " + e.getMessage());
        }
        if (!root.has("schema_version") || !root.get("schema_version").isJsonPrimitive()
                || !root.getAsJsonPrimitive("schema_version").isNumber() || !root.get("schema_version").getAsString().equals("1"))
            throw fail(source, "schema_version must be integer 1");
        JsonObject q = object(root.get("quilt_loader"), source, "quilt_loader");
        for (String key : q.keySet()) if (!LOADER_KEYS.contains(key)) throw fail(source, "unsupported quilt_loader." + key);
        String id = string(q, "id", source);
        String group = string(q, "group", source);
        if (id.equals("quilt_loader")) throw fail(source, "quilt_loader is owned by the host API provider");
        if ((id.equals("quilt_base") || id.equals("quilt_lifecycle_events")) && !managedQsl)
            throw fail(source, "managed QSL module digest mismatch for " + id);
        if (!id.matches("[a-z][a-z0-9_-]{1,63}")) throw fail(source, "invalid quilt_loader.id " + id);
        if (group.isBlank()) throw fail(source, "empty quilt_loader.group");
        String version = string(q, "version", source);
        if (!"net.fabricmc:intermediary".equals(string(q, "intermediate_mappings", source)))
            throw fail(source, "only explicit net.fabricmc:intermediary mappings are supported");
        rejectNonempty(q, "language_adapters", source);
        rejectNonempty(q, "jars", source);
        rejectNonempty(q, "provides", source);
        if (q.has("load_type") && !string(q, "load_type", source).equals("always")
                && !(managedQsl && string(q, "load_type", source).equals("if_possible")))
            throw fail(source, "unsupported quilt_loader.load_type (only always; pinned managed QSL if_possible is explicitly required)");

        JsonObject fabric = new JsonObject();
        fabric.addProperty("schemaVersion", 1); fabric.addProperty("id", id); fabric.addProperty("version", version);
        JsonObject custom = new JsonObject(); custom.add(RAW_KEY, root.deepCopy()); custom.addProperty("infinity:quilt_source", source);
        var chain = NativeQuiltSources.chain(source);
        if (!chain.isEmpty()) { JsonArray paths = new JsonArray(); chain.forEach(path -> paths.add(path.toString())); custom.add("infinity:quilt_source_chain", paths); }
        fabric.add("custom", custom);
        if (q.has("metadata")) {
            JsonObject meta = object(q.get("metadata"), source, "metadata");
            for (String key : List.of("name", "description")) if (meta.has(key)) string(meta, key, source);
            if (meta.has("license")) {
                JsonElement licenses = meta.get("license");
                for (JsonElement license : licenses.isJsonArray() ? licenses.getAsJsonArray() : List.of(licenses))
                    if (!license.isJsonPrimitive() || !license.getAsJsonPrimitive().isString()) throw fail(source, "only string license identifiers are supported");
            }
            if (meta.has("contact")) for (var contact : object(meta.get("contact"), source, "metadata.contact").entrySet())
                string(meta.getAsJsonObject("contact"), contact.getKey(), source);
            if (meta.has("contributors")) for (var contributor : object(meta.get("contributors"), source, "metadata.contributors").entrySet()) {
                JsonElement roles = contributor.getValue();
                for (JsonElement role : roles.isJsonArray() ? roles.getAsJsonArray() : List.of(roles))
                    if (!role.isJsonPrimitive() || !role.getAsJsonPrimitive().isString()) throw fail(source, "contributor roles must be strings");
            }
            if (meta.has("icon")) {
                JsonElement icon = meta.get("icon");
                if (icon.isJsonObject()) {
                    for (var entry : icon.getAsJsonObject().entrySet()) {
                        if (!entry.getKey().matches("[1-9][0-9]{0,8}")) throw fail(source, "icon size must be positive integer");
                        resource(string(icon.getAsJsonObject(), entry.getKey(), source), source);
                    }
                } else resource(string(meta, "icon", source), source);
            }
            for (String key : List.of("name", "description", "license", "icon", "contact"))
                if (meta.has(key)) fabric.add(key, meta.get(key).deepCopy());
        }
        String environment = "*";
        if (root.has("minecraft")) {
            JsonObject mc = object(root.get("minecraft"), source, "minecraft");
            if (mc.has("environment")) environment = side(string(mc, "environment", source), source);
        }
        fabric.addProperty("environment", environment);
        if (q.has("entrypoints")) {
            JsonObject projected = new JsonObject();
            for (var entry : object(q.get("entrypoints"), source, "entrypoints").entrySet()) {
                JsonArray result = new JsonArray();
                JsonElement value = entry.getValue();
                Iterable<JsonElement> values = value.isJsonArray() ? value.getAsJsonArray() : List.of(value);
                for (JsonElement ep : values) {
                    if (ep.isJsonPrimitive() && ep.getAsJsonPrimitive().isString()) result.add(entrypoint(ep.getAsString(), source));
                    else {
                        JsonObject obj = object(ep, source, "entrypoint " + entry.getKey());
                        for (String k : obj.keySet()) if (!Set.of("adapter", "value").contains(k)) throw fail(source, "unsupported entrypoint field " + k);
                        if (obj.has("adapter") && !string(obj, "adapter", source).equals("default")) throw fail(source, "custom Quilt language adapters are not supported");
                        result.add(entrypoint(string(obj, "value", source), source));
                    }
                }
                projected.add(entry.getKey(), result);
            }
            fabric.add("entrypoints", projected);
        }
        projectDependencies(q, fabric, "depends", source);
        projectDependencies(q, fabric, "breaks", source);
        if (root.has("mixin")) {
            JsonArray configs = new JsonArray(); JsonElement value = root.get("mixin");
            for (JsonElement item : value.isJsonArray() ? value.getAsJsonArray() : List.of(value)) {
                JsonObject config = new JsonObject();
                if (item.isJsonPrimitive() && item.getAsJsonPrimitive().isString()) config.addProperty("config", resource(item.getAsString(), source));
                else {
                    JsonObject obj = object(item, source, "mixin");
                    for (String key : obj.keySet()) if (!Set.of("config", "environment").contains(key)) throw fail(source, "unsupported mixin field " + key);
                    config.addProperty("config", resource(string(obj, "config", source), source));
                    if (obj.has("environment")) config.addProperty("environment", side(string(obj, "environment", source), source));
                }
                configs.add(config);
            }
            fabric.add("mixins", configs);
        }
        if (root.has("access_widener")) {
            JsonElement value = root.get("access_widener");
            if (value.isJsonArray()) {
                if (value.getAsJsonArray().size() != 1) throw fail(source, "exactly one access_widener is currently supported");
                value = value.getAsJsonArray().get(0);
            }
            if (!value.isJsonPrimitive() || !value.getAsJsonPrimitive().isString()) throw fail(source, "access_widener must name a resource");
            fabric.addProperty("accessWidener", resource(value.getAsString(), source));
        }
        return ModMetadataParser.parseMetadata(new ByteArrayInputStream(fabric.toString().getBytes(StandardCharsets.UTF_8)), source,
                List.of(), versions, dependencies, false);
    }

    private static void projectDependencies(JsonObject q, JsonObject fabric, String kind, String source) throws IOException {
        if (!q.has(kind)) return;
        JsonElement input = q.get(kind);
        if (!input.isJsonArray()) throw fail(source, kind + " must be an array");
        JsonObject projected = new JsonObject();
        for (JsonElement dependency : input.getAsJsonArray()) {
            String id; JsonElement ranges = new JsonPrimitive("*");
            if (dependency.isJsonPrimitive() && dependency.getAsJsonPrimitive().isString()) id = dependency.getAsString();
            else {
                JsonObject obj = object(dependency, source, kind + " dependency (nested alternatives are unsupported)");
                for (String key : obj.keySet()) if (!Set.of("id", "versions", "reason", "optional").contains(key)) throw fail(source, "unsupported dependency field " + key);
                id = string(obj, "id", source);
                if (obj.has("optional") && (!obj.get("optional").isJsonPrimitive() || !obj.getAsJsonPrimitive("optional").isBoolean() || obj.get("optional").getAsBoolean()))
                    throw fail(source, "optional dependencies are unsupported");
                if (obj.has("reason")) string(obj, "reason", source);
                if (obj.has("versions")) ranges = obj.get("versions");
            }
            if (!id.matches("[a-z][a-z0-9_-]{1,63}")) throw fail(source, "group-qualified or invalid dependency id " + id);
            if (projected.has(id)) throw fail(source, "repeated dependency " + id + " requires unsupported conjunction semantics");
            if (ranges.isJsonObject()) {
                JsonObject obj = ranges.getAsJsonObject();
                if (obj.size() != 1 || !obj.has("any") || !obj.get("any").isJsonArray()) throw fail(source, "only flat versions.any is supported");
                ranges = obj.get("any");
            }
            JsonArray versions = new JsonArray();
            for (JsonElement range : ranges.isJsonArray() ? ranges.getAsJsonArray() : List.of(ranges)) {
                if (!range.isJsonPrimitive() || !range.getAsJsonPrimitive().isString() || range.getAsString().isBlank()) throw fail(source, "version constraint must be nonempty string");
                String constraint = range.getAsString();
                if (!constraint.equals("*")) {
                    if (constraint.charAt(0) >= '0' && constraint.charAt(0) <= '9')
                        throw fail(source, "unsupported bare semantic version constraint " + constraint
                                + ": Quilt uses caret-range semantics; an explicit supported comparator is required");
                    boolean ordinary = constraint.matches("(?:=|>=|<=|>|<)[0-9]+(?:\\.[0-9]+){0,2}(?:-[0-9A-Za-z.-]+)?(?:\\+[0-9A-Za-z.-]+)?");
                    // Quilt 0.30.1 and FFLoader both retain an empty-but-present prerelease:
                    // 0.16.0- < 0.16.0-0 < 0.16.0. Do not remove the dash or use -0.
                    // This extension is bounded to our semantic, host-owned loader provider.
                    // Arbitrary dependency candidates can be raw versions: Quilt orders those
                    // using FlexVer whereas FFLoader does not. Bare Quilt versions also have
                    // caret semantics, so only explicit comparisons are admitted here.
                    boolean loaderEmptyPrerelease = id.equals("quilt_loader")
                            && constraint.matches("(?:=|>=|<=|>|<)[0-9]+(?:\\.[0-9]+){0,2}-(?:\\+[0-9A-Za-z.-]+)?");
                    if (!ordinary && !loaderEmptyPrerelease)
                        throw fail(source, "unsupported semantic version constraint " + constraint);
                    String rawVersion = constraint.replaceFirst("^[<>=]+", "");
                    try { net.fabricmc.loader.api.SemanticVersion.parse(rawVersion); }
                    catch (net.fabricmc.loader.api.VersionParsingException e) { throw fail(source, "invalid semantic version constraint " + constraint); }
                }
                versions.add(range);
            }
            if (versions.isEmpty()) throw fail(source, "empty version alternatives");
            projected.add(id, versions);
        }
        fabric.add(kind, projected);
    }

    private static String entrypoint(String value, String source) throws IOException {
        if (!value.matches("[A-Za-z_$][A-Za-z0-9_$]*(?:\\.[A-Za-z_$][A-Za-z0-9_$]*)*(?:::[A-Za-z_$][A-Za-z0-9_$]*)?"))
            throw fail(source, "invalid default Java entrypoint " + value);
        return value;
    }
    private static String side(String value, String source) throws IOException {
        return switch (value) { case "*", "client" -> value; case "dedicated_server" -> "server"; default -> throw fail(source, "unsupported environment " + value); };
    }
    private static String resource(String value, String source) throws IOException {
        if (value.isBlank() || value.startsWith("/") || value.contains("\\") || Arrays.asList(value.split("/", -1)).stream().anyMatch(p -> p.isEmpty() || p.equals(".") || p.equals("..")) || value.contains(":"))
            throw fail(source, "unsafe resource path " + value);
        return value;
    }
    private static void rejectNonempty(JsonObject q, String key, String source) throws IOException {
        if (!q.has(key)) return;
        JsonElement value = q.get(key);
        if (key.equals("language_adapters") ? !value.isJsonObject() : !value.isJsonArray())
            throw fail(source, "invalid type for quilt_loader." + key);
        if ((value.isJsonObject() && value.getAsJsonObject().isEmpty()) || (value.isJsonArray() && value.getAsJsonArray().isEmpty())) return;
        throw fail(source, "unsupported quilt_loader." + key);
    }
    private static JsonObject object(JsonElement value, String source, String name) throws IOException {
        if (value == null || !value.isJsonObject()) throw fail(source, name + " must be object");
        return value.getAsJsonObject();
    }
    private static String string(JsonObject obj, String name, String source) throws IOException {
        JsonElement value = obj.get(name);
        if (value == null || !value.isJsonPrimitive() || !value.getAsJsonPrimitive().isString()) throw fail(source, name + " must be string");
        return value.getAsString();
    }
    private static JsonElement readStrict(JsonReader reader, int depth) throws IOException {
        if (depth > 64) throw new IOException("JSON nesting exceeds 64 at " + reader.getPath());
        switch (reader.peek()) {
            case BEGIN_OBJECT: {
                reader.beginObject(); JsonObject result = new JsonObject();
                while (reader.hasNext()) { String key = reader.nextName(); if (result.has(key)) throw new IOException("duplicate key " + key + " at " + reader.getPath()); result.add(key, readStrict(reader, depth + 1)); }
                reader.endObject(); return result;
            }
            case BEGIN_ARRAY: {
                reader.beginArray(); JsonArray result = new JsonArray();
                while (reader.hasNext()) { if (result.size() >= 10000) throw new IOException("oversized array"); result.add(readStrict(reader, depth + 1)); }
                reader.endArray(); return result;
            }
            case STRING: return new JsonPrimitive(reader.nextString());
            case NUMBER: return new JsonPrimitive(new java.math.BigDecimal(reader.nextString()));
            case BOOLEAN: return new JsonPrimitive(reader.nextBoolean());
            case NULL: reader.nextNull(); return JsonNull.INSTANCE;
            default: throw new IOException("unexpected token at " + reader.getPath());
        }
    }
    private static IOException fail(String source, String reason) { return new IOException("Native Quilt " + PROFILE + " [" + source + "]: " + reason); }
}
