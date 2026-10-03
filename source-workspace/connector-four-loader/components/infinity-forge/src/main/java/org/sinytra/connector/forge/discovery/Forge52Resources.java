package org.sinytra.connector.forge.discovery;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.jar.Manifest;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.ClassNode;
import org.sinytra.connector.forge.transform.Forge52Symbols;

/** Bounded same-JAR service and direct-Mojmap Mixin resource admission. */
public final class Forge52Resources {
    private Forge52Resources() {}
    public record Plan(List<String> mixins, List<String> services, Map<String, Object> audit) {
        public static Plan empty() { return new Plan(List.of(), List.of(), Map.of()); }
    }

    public static Plan inspect(Map<String, byte[]> entries) throws java.io.IOException {
        List<String> services = new ArrayList<>();
        Map<String, List<String>> providers = new LinkedHashMap<>();
        for (var entry : entries.entrySet()) {
            if (!entry.getKey().startsWith("META-INF/services/")) continue;
            String service = entry.getKey().substring("META-INF/services/".length());
            requireName(service, "service");
            ClassNode contract = readClass(entries, service);
            if ((contract.access & Opcodes.ACC_INTERFACE) == 0) throw Forge52Symbols.unsupported("service contract must be a same-JAR interface: " + service);
            List<String> implementations = new ArrayList<>();
            for (String raw : new String(entry.getValue(), StandardCharsets.UTF_8).split("\\R")) {
                String name = raw.split("#", 2)[0].trim(); if (name.isEmpty()) continue;
                requireName(name, "service provider");
                ClassNode implementation = readClass(entries, name);
                if ((implementation.access & Opcodes.ACC_PUBLIC) == 0 || (implementation.access & (Opcodes.ACC_ABSTRACT | Opcodes.ACC_INTERFACE)) != 0)
                    throw Forge52Symbols.unsupported("service provider must be public/concrete: " + name);
                if (implementation.methods.stream().noneMatch(m -> m.name.equals("<init>") && m.desc.equals("()V") && (m.access & Opcodes.ACC_PUBLIC) != 0))
                    throw Forge52Symbols.unsupported("service provider needs public zeroarg constructor: " + name);
                if (!implementsInterface(entries, implementation.name, service.replace('.', '/'), new LinkedHashSet<>()))
                    throw Forge52Symbols.unsupported("service provider does not implement same-JAR contract: " + name + " -> " + service);
                if (!implementations.contains(name)) implementations.add(name);
            }
            if (implementations.isEmpty()) throw Forge52Symbols.unsupported("empty service descriptor: " + service);
            services.add(service); providers.put(service, implementations);
        }
        LinkedHashSet<String> configs = new LinkedHashSet<>();
        byte[] manifestBytes = entries.get("META-INF/MANIFEST.MF");
        if (manifestBytes != null) {
            var manifest = new Manifest(new ByteArrayInputStream(manifestBytes));
            String names = manifest.getMainAttributes().getValue("MixinConfigs");
            if (names != null) for (String name : names.split(",", -1)) {
                name = name.trim(); requireResource(name, "Mixin config");
                if (!configs.add(name)) throw Forge52Symbols.unsupported("duplicate Mixin config " + name);
            }
        }
        Map<String, Object> mixinAudit = new LinkedHashMap<>();
        for (String name : configs) {
            byte[] bytes = entries.get(name);
            if (bytes == null) throw Forge52Symbols.unsupported("missing declared Mixin config " + name);
            if (bytes.length > 1024 * 1024) throw Forge52Symbols.unsupported("oversized Mixin config " + name);
            JsonObject json;
            try { json = JsonParser.parseString(new String(bytes, StandardCharsets.UTF_8)).getAsJsonObject(); }
            catch (RuntimeException error) { throw Forge52Symbols.unsupported("invalid Mixin JSON " + name); }
            if (json.has("plugin")) throw Forge52Symbols.unsupported("Mixin config plugins: " + name);
            String pkg = json.has("package") ? json.get("package").getAsString() : "";
            requireName(pkg, "Mixin package");
            List<String> classes = new ArrayList<>();
            for (String side : List.of("mixins", "client", "server")) {
                if (!json.has(side)) continue;
                if (!json.get(side).isJsonArray()) throw Forge52Symbols.unsupported("invalid Mixin class list " + name + ":" + side);
                for (var value : json.getAsJsonArray(side)) {
                    String cls = pkg + "." + value.getAsString(); requireName(cls, "Mixin class");
                    readClass(entries, cls); classes.add(cls);
                }
            }
            if (classes.isEmpty()) throw Forge52Symbols.unsupported("empty Mixin class list " + name);
            Map<String, Object> detail = new LinkedHashMap<>(); detail.put("classes", classes);
            detail.put("namespace", "direct Mojmap; config and annotations preserved");
            if (json.has("refmap")) {
                String refmap = json.get("refmap").getAsString(); requireResource(refmap, "Mixin refmap");
                detail.put("refmap", refmap); detail.put("refmapPresent", entries.containsKey(refmap));
                // A real refmap is a distinct remapping contract. The reviewed Forge
                // production Clumps artifact declares a refmap that is absent; do
                // not invent one or silently apply intermediary/SRG translations.
                if (entries.containsKey(refmap)) throw Forge52Symbols.unsupported("Forge refmap translation is not implemented: " + refmap);
                detail.put("refmapTreatment", "upstream absent resource preserved; native host Mixin remains authoritative");
            }
            mixinAudit.put(name, detail);
        }
        Map<String, Object> audit = new LinkedHashMap<>();
        audit.put("sameJarServiceProviders", providers); audit.put("nativeMixinConfigs", mixinAudit);
        return new Plan(List.copyOf(configs), List.copyOf(services), audit);
    }

    private static boolean implementsInterface(Map<String, byte[]> entries, String type, String target, Set<String> seen) {
        if (type.equals(target)) return true;
        if (!seen.add(type)) return false;
        byte[] bytes = entries.get(type + ".class"); if (bytes == null) return false;
        ClassReader reader = new ClassReader(bytes);
        for (String iface : reader.getInterfaces()) if (implementsInterface(entries, iface, target, seen)) return true;
        return reader.getSuperName() != null && implementsInterface(entries, reader.getSuperName(), target, seen);
    }

    private static ClassNode readClass(Map<String, byte[]> entries, String name) {
        byte[] bytes = entries.get(name.replace('.', '/') + ".class");
        if (bytes == null) throw Forge52Symbols.unsupported("resource contract class is not in this JAR: " + name);
        ClassNode node = new ClassNode(); new ClassReader(bytes).accept(node, ClassReader.SKIP_CODE | ClassReader.SKIP_DEBUG | ClassReader.SKIP_FRAMES);
        if (!node.name.equals(name.replace('.', '/'))) throw Forge52Symbols.unsupported("class name/path mismatch " + name);
        return node;
    }

    private static void requireName(String name, String label) {
        if (!name.matches("[A-Za-z_$][A-Za-z0-9_$]*(\\.[A-Za-z_$][A-Za-z0-9_$]*)+")) throw Forge52Symbols.unsupported("invalid " + label + " " + name);
        if (name.startsWith("net.minecraftforge.") || name.startsWith("net.neoforged.") || name.startsWith("java.") || name.startsWith("org.sinytra.connector."))
            throw Forge52Symbols.unsupported("reserved " + label + " " + name);
    }

    private static void requireResource(String name, String label) {
        if (name.isBlank() || name.startsWith("/") || name.contains("\\") || name.contains("..") || name.contains(":") || name.contains("//"))
            throw Forge52Symbols.unsupported("invalid " + label + " path " + name);
    }
}
