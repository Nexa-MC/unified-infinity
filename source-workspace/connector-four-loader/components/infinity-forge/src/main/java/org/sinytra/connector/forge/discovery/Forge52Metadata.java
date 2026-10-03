package org.sinytra.connector.forge.discovery;

import com.electronwill.nightconfig.core.Config;
import com.electronwill.nightconfig.toml.TomlFormat;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.apache.maven.artifact.versioning.DefaultArtifactVersion;
import org.apache.maven.artifact.versioning.VersionRange;
import org.sinytra.connector.forge.transform.Forge52Symbols;

/** Preserve Forge constraints while projecting their effective host identities. */
public final class Forge52Metadata {
    public static final String FORGE_VERSION = "52.1.0";
    public static final String CAPABILITY = "unified_forge52_adapter";
    public static final String PROVIDER = "unified_forge_52";
    public static final String PROVIDER_VERSION = "1.0.0";
    private Forge52Metadata() {}

    public record Projection(String toml, Map<String, Object> audit) {}

    public static Projection project(String original, String side) {
        return project(original, side, Forge52Resources.Plan.empty());
    }

    public static Projection project(String original, String side, Forge52Resources.Plan resources) {
        Config config = TomlFormat.instance().createParser().parse(original);
        String loader = requiredString(config, "modLoader");
        if (!loader.equals("javafml")) throw Forge52Symbols.unsupported("modLoader=" + loader);
        String loaderRange = requiredString(config, "loaderVersion");
        requireVersion("Forge javafml ABI", loaderRange, FORGE_VERSION);
        if (!(config.get("license") instanceof String license) || license.isBlank())
            throw Forge52Symbols.unsupported("missing nonempty license");
        for (String unsupported : List.of("services", "mixins", "accessTransformers", "coremods"))
            if (config.contains(unsupported)) throw Forge52Symbols.unsupported("metadata " + unsupported);
        Object modValue = config.get("mods");
        if (!(modValue instanceof List<?> mods) || mods.isEmpty())
            throw Forge52Symbols.unsupported("missing [[mods]]");
        Set<String> ids = new java.util.HashSet<>();
        for (Object value : mods) {
            if (!(value instanceof Config mod)) throw Forge52Symbols.unsupported("invalid [[mods]] entry");
            String id = requiredString(mod, "modId");
            if (!id.matches("[a-z][a-z0-9_]{1,63}") || !ids.add(id))
                throw Forge52Symbols.unsupported("invalid or duplicate modId " + id);
            if (Set.of("minecraft", "neoforge", CAPABILITY).contains(id))
                throw Forge52Symbols.unsupported("reserved modId " + id);
        }
        List<Map<String, Object>> dependencyAudit = new ArrayList<>();
        Object dependencyValue = config.get("dependencies");
        if (dependencyValue != null && !(dependencyValue instanceof Config))
            throw Forge52Symbols.unsupported("invalid dependencies table");
        if (dependencyValue instanceof Config dependencies) {
            for (String owner : dependencies.valueMap().keySet()) {
                if (!ids.contains(owner)) throw Forge52Symbols.unsupported("dependencies for undeclared mod " + owner);
                Object listValue = dependencies.get(owner);
                if (!(listValue instanceof List<?> list)) throw Forge52Symbols.unsupported("dependencies must be an array for " + owner);
                for (Object value : list) {
                    if (!(value instanceof Config dep)) throw Forge52Symbols.unsupported("invalid dependency for " + owner);
                    String id = requiredString(dep, "modId");
                    Object mandatory = dep.get("mandatory");
                    if (!(mandatory instanceof Boolean required))
                        throw Forge52Symbols.unsupported("dependency " + owner + " -> " + id + " missing boolean mandatory");
                    if (dep.contains("type")) throw Forge52Symbols.unsupported("mixed Forge/Neo dependency type for " + id);
                    String range = dep.getOrElse("versionRange", "");
                    String dependencySide = dep.getOrElse("side", "BOTH");
                    String ordering = dep.getOrElse("ordering", "NONE");
                    if (!Set.of("BOTH", "CLIENT", "SERVER").contains(dependencySide))
                        throw Forge52Symbols.unsupported("dependency side " + dependencySide);
                    if (!Set.of("NONE", "BEFORE", "AFTER").contains(ordering))
                        throw Forge52Symbols.unsupported("dependency ordering " + ordering);
                    validateRange(range);
                    boolean applicable = dependencySide.equals("BOTH") || dependencySide.equals(side);
                    if (applicable && id.equals("forge")) requireVersion("Forge adapter capability", range, FORGE_VERSION);
                    if (applicable && id.equals("minecraft")) requireVersion("Minecraft", range, "1.21.1");
                    Map<String, Object> audit = new LinkedHashMap<>();
                    audit.put("owner", owner); audit.put("originalModId", id);
                    audit.put("effectiveModId", id.equals("forge") ? CAPABILITY : id);
                    audit.put("mandatory", required); audit.put("effectiveType", required ? "required" : "optional");
                    audit.put("versionRange", range); audit.put("ordering", ordering); audit.put("side", dependencySide);
                    audit.put("appliesToCurrentSide", applicable);
                    dependencyAudit.add(audit);
                    if (id.equals("forge")) dep.set("modId", CAPABILITY);
                    dep.remove("mandatory");
                    dep.set("type", required ? "required" : "optional");
                }
            }
        }
        // Feature tables keep their original bounds and remain subject to FML's
        // final ForgeFeature checks. Reject a known unsatisfied JVM bound early.
        Object featuresValue = config.get("features");
        if (featuresValue instanceof Config features) {
            for (String id : features.valueMap().keySet()) {
                if (!ids.contains(id)) throw Forge52Symbols.unsupported("features for undeclared mod " + id);
                Object featureValue = features.get(id);
                if (!(featureValue instanceof Config feature)) throw Forge52Symbols.unsupported("invalid features table for " + id);
                Object javaRange = feature.get("javaVersion");
                if (javaRange != null) requireVersion("Java", javaRange.toString(), Integer.toString(Runtime.version().feature()));
            }
        }
        // FML builds automatic modules: same-JAR service providers come from
        // META-INF/services and automatic modules can use services implicitly.
        // Adding a TOML services/uses list makes Java reject the descriptor.
        if (!resources.mixins().isEmpty()) {
            List<Config> mixins = new ArrayList<>();
            for (String name : resources.mixins()) {
                Config entry = Config.inMemory(); entry.set("config", name); mixins.add(entry);
            }
            config.set("mixins", mixins);
        }
        config.set("modLoader", PROVIDER);
        config.set("loaderVersion", "[" + PROVIDER_VERSION + "]");
        Map<String, Object> audit = new LinkedHashMap<>();
        audit.put("sourceLoader", loader); audit.put("sourceLoaderRange", loaderRange);
        audit.put("capabilityModId", CAPABILITY); audit.put("capabilityVersion", FORGE_VERSION);
        audit.put("effectiveLoader", PROVIDER); audit.put("effectiveLoaderVersion", PROVIDER_VERSION);
        audit.put("dependencies", dependencyAudit); audit.put("sourceNamespace", "Mojmap-Forge52-production");
        audit.put("capabilityScope", "explicit audited API slice; not complete Forge 52 support");
        return new Projection(TomlFormat.instance().createWriter().writeToString(config), audit);
    }

    private static String requiredString(Config config, String key) {
        Object value = config.get(key);
        if (!(value instanceof String string) || string.isBlank()) throw Forge52Symbols.unsupported("missing string " + key);
        return string;
    }

    private static VersionRange validateRange(String range) {
        try { return VersionRange.createFromVersionSpec(range); }
        catch (Exception e) { throw Forge52Symbols.unsupported("invalid version range " + range); }
    }

    private static void requireVersion(String label, String range, String version) {
        if (!validateRange(range).containsVersion(new DefaultArtifactVersion(version)))
            throw Forge52Symbols.unsupported(label + " version " + version + " does not satisfy " + range);
    }
}
