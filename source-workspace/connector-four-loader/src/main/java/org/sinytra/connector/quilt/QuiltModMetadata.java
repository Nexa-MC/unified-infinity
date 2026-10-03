package org.sinytra.connector.quilt;

import org.quiltmc.loader.api.*;
import org.sinytra.connector.quilt.metadata.qmj.ModLicenseImpl;

import java.util.*;

/** Exact Quilt identity and values retained alongside the host's bounded dependency projection. */
public final class QuiltModMetadata implements ModMetadata {
    private final net.fabricmc.loader.api.metadata.ModMetadata host;
    private final Map<String, LoaderValue> values;
    private final LoaderValue.LObject loader;
    private final Map<String, LoaderValue> details;

    QuiltModMetadata(net.fabricmc.loader.api.metadata.ModMetadata host) {
        this.host = host;
        var original = host.getCustomValue(QuiltBridge.METADATA_KEY);
        if (original != null) {
            values = QuiltValues.from(original, "quilt.mod.json:$").asObject();
            loader = Objects.requireNonNull(values.get("quilt_loader"), "quilt_loader").asObject();
            var meta = loader.get("metadata");
            details = meta == null ? Map.of() : meta.asObject();
        } else {
            Map<String, LoaderValue> custom = new LinkedHashMap<>();
            host.getCustomValues().forEach((k, v) -> custom.put(k, QuiltValues.from(v, "fabric.mod.json:custom." + k)));
            values = Collections.unmodifiableMap(custom);
            loader = null;
            details = Map.of();
        }
    }

    public boolean nativeQuilt() { return loader != null; }
    public String id() { return nativeQuilt() ? loader.get("id").asString() : host.getId(); }
    public String group() { return nativeQuilt() ? loader.get("group").asString() : ""; }
    public Version version() { return Version.of(nativeQuilt() ? loader.get("version").asString() : host.getVersion().getFriendlyString()); }
    public String name() { return nativeQuilt() ? string(details, "name", id()) : host.getName(); }
    public String description() { return nativeQuilt() ? string(details, "description", "") : host.getDescription(); }
    public Collection<ModLicense> licenses() {
        if (!nativeQuilt()) return host.getLicense().stream().map(ModLicense::fromIdentifierOrDefault).toList();
        var value = details.get("license");
        if (value == null) return List.of();
        var list = value.type() == LoaderValue.LType.ARRAY ? value.asArray() : List.of(value);
        return list.stream().map(v -> {
            if (v.type() == LoaderValue.LType.STRING) return ModLicense.fromIdentifierOrDefault(v.asString());
            var o = v.asObject();
            return (ModLicense) new ModLicenseImpl(string(o, "name", string(o, "id", "")), string(o, "id", ""), string(o, "url", ""), string(o, "description", ""));
        }).toList();
    }
    public Collection<ModContributor> contributors() {
        if (!nativeQuilt()) {
            List<ModContributor> result = new ArrayList<>();
            host.getAuthors().forEach(p -> result.add(ModContributor.of(p.getName(), List.of("Author"))));
            host.getContributors().forEach(p -> result.add(ModContributor.of(p.getName(), List.of("Contributor"))));
            return List.copyOf(result);
        }
        var value = details.get("contributors");
        if (value == null) return List.of();
        List<ModContributor> result = new ArrayList<>();
        value.asObject().forEach((name, roles) -> result.add(ModContributor.of(name,
            roles.type() == LoaderValue.LType.ARRAY ? roles.asArray().stream().map(LoaderValue::asString).toList() : List.of(roles.asString()))));
        return List.copyOf(result);
    }
    public String getContactInfo(String key) { return contactInfo().get(key); }
    public Map<String, String> contactInfo() {
        if (!nativeQuilt()) return Map.copyOf(host.getContact().asMap());
        var contact = details.get("contact");
        if (contact == null) return Map.of();
        Map<String, String> result = new LinkedHashMap<>();
        contact.asObject().forEach((key, value) -> result.put(key, value.asString()));
        return Collections.unmodifiableMap(result);
    }
    public Collection<ModDependency> depends() { return dependencies("depends", net.fabricmc.loader.api.metadata.ModDependency.Kind.DEPENDS); }
    public Collection<ModDependency> breaks() { return dependencies("breaks", net.fabricmc.loader.api.metadata.ModDependency.Kind.BREAKS); }
    private Collection<ModDependency> dependencies(String field, net.fabricmc.loader.api.metadata.ModDependency.Kind kind) {
        if (nativeQuilt()) {
            var value = loader.get(field);
            if (value == null) return List.of();
            return value.asArray().stream().map(v -> dependency(v, field.equals("breaks"))).toList();
        }
        return host.getDependencies().stream().filter(d -> d.getKind() == kind).map(d -> {
            List<VersionInterval> intervals = d.getVersionIntervals().stream().map(i -> VersionInterval.of(
                i.getMin() == null ? null : Version.of(i.getMin().getFriendlyString()), i.isMinInclusive(),
                i.getMax() == null ? null : Version.of(i.getMax().getFriendlyString()), i.isMaxInclusive())).toList();
            return (ModDependency) ModDependency.Only.of(d.getModId(), VersionRange.ofIntervals(intervals));
        }).toList();
    }
    private static ModDependency dependency(LoaderValue value, boolean breaks) {
        if (value.type() == LoaderValue.LType.ARRAY) {
            List<ModDependency.Only> alternatives = value.asArray().stream().map(v -> (ModDependency.Only) dependency(v, breaks)).toList();
            return breaks ? ModDependency.All.of(alternatives) : ModDependency.Any.of(alternatives);
        }
        if (value.type() == LoaderValue.LType.STRING) return ModDependency.Only.of(identifier(value.asString()));
        var object = value.asObject();
        var unless = object.get("unless");
        return ModDependency.Only.of(identifier(object.get("id").asString()), range(object.get("versions")), string(object, "reason", ""),
            unless == null ? null : dependency(unless, false), object.containsKey("optional") && object.get("optional").asBoolean());
    }
    private static ModDependencyIdentifier identifier(String id) {
        int colon = id.indexOf(':');
        return colon < 0 ? ModDependencyIdentifier.of("", id) : ModDependencyIdentifier.of(id.substring(0, colon), id.substring(colon + 1));
    }
    static VersionRange range(LoaderValue value) {
        if (value == null) return VersionRange.ANY;
        if (value.type() == LoaderValue.LType.ARRAY) return VersionRange.ofRanges(value.asArray().stream().map(QuiltModMetadata::range).toList());
        if (value.type() == LoaderValue.LType.OBJECT) {
            var object = value.asObject();
            if (object.containsKey("any")) return range(object.get("any"));
            if (object.containsKey("all")) {
                VersionRange result = VersionRange.ANY;
                for (LoaderValue element : object.get("all").asArray()) result = result.combineMatchingBoth(range(element));
                return result;
            }
            throw new UnsupportedOperationException("Unsupported Quilt version object at " + value.location());
        }
        String text = value.asString().trim();
        if (text.equals("*")) return VersionRange.ANY;
        String operator = "=";
        for (String candidate : List.of(">=", "<=", ">", "<", "=")) if (text.startsWith(candidate)) { operator = candidate; text = text.substring(candidate.length()).trim(); break; }
        if (text.startsWith("~") || text.startsWith("^") || text.indexOf('*') >= 0 || text.contains(" ") || text.contains("||"))
            throw new UnsupportedOperationException("Native Quilt first slice does not expose this version constraint: " + value.asString());
        Version version = Version.of(text);
        return switch (operator) {
            case ">=" -> VersionRange.ofInterval(version, true, null, false);
            case ">" -> VersionRange.ofInterval(version, false, null, false);
            case "<=" -> VersionRange.ofInterval(null, false, version, true);
            case "<" -> VersionRange.ofInterval(null, false, version, false);
            default -> VersionRange.ofExact(version);
        };
    }
    public Collection<? extends ProvidedMod> provides() {
        if (nativeQuilt()) {
            var value = loader.get("provides");
            if (value == null) return List.of();
            return value.asArray().stream().map(v -> {
                if (v.type() == LoaderValue.LType.STRING) {
                    var id = identifier(v.asString());
                    return new Provided(id.mavenGroup().isEmpty() ? group() : id.mavenGroup(), id.id(), version());
                }
                var o = v.asObject(); var id = identifier(o.get("id").asString());
                return new Provided(string(o, "group", id.mavenGroup().isEmpty() ? group() : id.mavenGroup()), id.id(), o.containsKey("version") ? Version.of(o.get("version").asString()) : version());
            }).toList();
        }
        return host.getProvides().stream().map(id -> new Provided("", id, version())).toList();
    }
    private record Provided(String group, String id, Version version) implements ProvidedMod {}
    public String icon(int size) {
        if (!nativeQuilt()) return host.getIconPath(size).orElse(null);
        var value = details.get("icon");
        if (value == null) return null;
        if (value.type() == LoaderValue.LType.STRING) return value.asString();
        NavigableMap<Integer, String> icons = new TreeMap<>();
        value.asObject().forEach((s, path) -> icons.put(Integer.parseInt(s), path.asString()));
        var selected = icons.ceilingEntry(size);
        if (selected == null) selected = icons.lastEntry();
        return selected == null ? null : selected.getValue();
    }
    public boolean containsValue(String key) { return values.containsKey(key); }
    public LoaderValue value(String key) { return values.get(key); }
    public Map<String, LoaderValue> values() { return values; }
    private static String string(Map<String, LoaderValue> object, String key, String fallback) { var value = object.get(key); return value == null ? fallback : value.asString(); }
}
