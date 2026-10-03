package org.sinytra.connector.transformer.quilt;

import net.fabricmc.loader.api.SemanticVersion;
import net.fabricmc.loader.api.Version;
import net.fabricmc.loader.api.metadata.ModDependency;
import net.fabricmc.loader.api.metadata.version.VersionPredicate;
import net.fabricmc.loader.impl.metadata.*;

import java.io.*;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.jar.JarFile;

/** Pure JVM coverage; the OP Tab archive is read as data and never put on a class path. */
public final class NativeQuiltPrereleaseRegression {
    private static final String QUILT_SHA256 = "a561a9fe9abb45556c696095a29e81477618bf2408b86c36db5aecdcd6a86fdb";
    private static final String FFLOADER_SHA256 = "dc8829a0d9b5fa19eb0c50d54c981445fb21cba2abd2a39c5ff0b58ff7d5c1e1";
    private static final String OPTAB_SHA256 = "6121446645d4521ddb5deae40e506fb02a7d4f06c0ce049fabc6ecaed548c296";
    private static final String DESCRIPTOR_SHA256 = "4c874ddde93bf8dce82d1e482a3a5280f96970ccf934a8b988818d39f55d7d3f";
    private static final String DESCRIPTOR = "/quilt/optab-2.0.0V1.21.1+1.21.quilt.mod.json";
    private static final List<String> BOUNDS = List.of("0.16.0-", "0.16.0-+build.1", "0.16-", "0-", "0.16.0", "0.31.0-");
    private static final List<String> OPERATORS = List.of(">=", ">", "<=", "<", "=");
    private static final List<String> VERSIONS = List.of("0.15.9", "0.16.0-", "0.16.0-+build.1", "0.16.0-0",
            "0.16.0-alpha", "0.16.0-alpha.1", "0.16.0-rc.1", "0.16.0", "0.16.0+build.1", "0.16.0.0",
            "0.16.0.1-", "0.16.1-", "0.30.1", "0.31.0-", "0.31.0-beta.1", "0.31.0", "1.0.0-", "1.0.0");
    private static int assertions;

    private static void check(boolean value, String message) {
        assertions++;
        if (!value) throw new AssertionError(message);
    }

    private static String sha256(byte[] bytes) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
    }

    private static LoaderModMetadata parse(byte[] bytes) throws Exception {
        Path config = Files.createTempDirectory("quilt-prerelease-regression");
        try {
            return NativeQuiltMetadata.parse(new ByteArrayInputStream(bytes), "original-quilt-descriptor",
                    new VersionOverrides(), new DependencyOverrides(config), false);
        } finally {
            Files.delete(config);
        }
    }

    private static LoaderModMetadata parse(String id, String range, String kind) throws Exception {
        return parse(("{\"schema_version\":1,\"quilt_loader\":{\"group\":\"dev.infinity\",\"id\":\"range-test\","
                + "\"version\":\"1.0.0\",\"intermediate_mappings\":\"net.fabricmc:intermediary\",\"" + kind
                + "\":[{\"id\":\"" + id + "\",\"versions\":\"" + range + "\"}]}}").getBytes(StandardCharsets.UTF_8));
    }

    static int run() throws Exception {
        assertions = 0;
        byte[] fixture;
        try (InputStream input = Objects.requireNonNull(NativeQuiltPrereleaseRegression.class.getResourceAsStream(DESCRIPTOR))) {
            fixture = input.readAllBytes();
        }
        check(sha256(fixture).equals(DESCRIPTOR_SHA256), "exact original OP Tab descriptor");
        checkOptab(parse(fixture));
        for (String bound : BOUNDS) for (String operator : OPERATORS) {
            String range = operator + bound;
            var metadata = parse("quilt_loader", range, "depends");
            var dependency = metadata.getDependencies().iterator().next();
            check(metadata.getCustomValue(NativeQuiltMetadata.RAW_KEY).getAsObject().get("quilt_loader")
                    .getAsObject().get("depends").getAsArray().get(0).getAsObject().get("versions").getAsString().equals(range),
                    "unchanged native constraint " + range);
            var predicate = dependency.getVersionRequirements().iterator().next();
            check(predicate.getTerms().iterator().next().getReferenceVersion().getFriendlyString().equals(bound),
                    "unchanged projected boundary " + range);
            for (String version : VERSIONS) {
                int comparison = SemanticVersion.parse(version).compareTo(SemanticVersion.parse(bound));
                boolean expected = switch (operator) {
                    case ">=" -> comparison >= 0;
                    case ">" -> comparison > 0;
                    case "<=" -> comparison <= 0;
                    case "<" -> comparison < 0;
                    default -> comparison == 0;
                };
                check(dependency.matches(Version.parse(version)) == expected, range + " vs " + version);
            }
        }
        var empty = parse("quilt_loader", ">=0.16.0-", "depends").getDependencies().iterator().next();
        check(!empty.matches(Version.parse("0.15.9")), "lower release rejected");
        check(empty.matches(Version.parse("0.16.0-")), "empty boundary included; must not become -0");
        check(empty.matches(Version.parse("0.16.0-alpha")), "prerelease included; must not remove dash");
        check(empty.matches(Version.parse("0.16.0")), "release included");
        var breaks = parse("quilt_loader", ">=0.16.0-", "breaks").getDependencies().iterator().next();
        check(breaks.getKind() == ModDependency.Kind.BREAKS && breaks.matches(Version.parse("0.30.1")), "breaks keeps boundary");
        for (String range : List.of("0.16.0-", "^0.16.0-", "~0.16.0-", ">=0.16.0- || <0.10.0",
                ">=0.16.0- <0.30.0", ">=0.16.0-.alpha", ">=0.16.0-+", ">=0.16.0- ", ">=0.16.0-alpha..1")) {
            reject("quilt_loader", range);
        }
        reject("arbitrary_dependency", ">=0.16.0-");
        testExplicitConstraintBoundary();
        return assertions;
    }

    private static void testExplicitConstraintBoundary() throws Exception {
        for (String id : List.of("quilt_loader", "arbitrary_dependency")) for (String kind : List.of("depends", "breaks")) {
            for (String version : List.of("1", "1.2", "1.2.3", "1.2.3-alpha.1", "1.2.3+build.1", "1.2.3-alpha.1+build.1")) {
                for (String operator : OPERATORS) {
                    var dependency = parse(id, operator + version, kind).getDependencies().iterator().next();
                    check(dependency.matches(Version.parse(version)) == List.of("=", ">=", "<=").contains(operator),
                            "explicit comparator boundary " + id + " " + kind + " " + operator + version);
                }
                try {
                    parse(id, version, kind);
                    throw new AssertionError("bare Quilt caret range accepted as equality: " + version);
                } catch (IOException expected) {
                    check(expected.getMessage().contains("unsupported bare semantic version constraint " + version)
                                    && expected.getMessage().contains("Quilt uses caret-range semantics"),
                            "actionable bare-version diagnostic: " + expected.getMessage());
                }
            }
            var exact = parse(id, "=1.2.3", kind).getDependencies().iterator().next();
            check(exact.matches(Version.parse("1.2.3")) && !exact.matches(Version.parse("1.2.4")), "explicit exact remains exact");
            check(parse(id, "*", kind).getDependencies().iterator().next().matches(Version.parse("9.9.9")), "wildcard remains accepted");
        }
    }

    private static void reject(String id, String range) throws Exception {
        try {
            parse(id, range, "depends");
            throw new AssertionError("unsupported range was admitted: " + id + " " + range);
        } catch (IOException expected) {
            check(expected.getMessage().contains("semantic version constraint"), expected.getMessage());
        }
    }

    private static void checkOptab(LoaderModMetadata metadata) throws Exception {
        check(metadata.getId().equals("optab"), "original OP Tab identity");
        check(metadata.getVersion().getFriendlyString().equals("2.0.0V1.21.1+1.21"), "original non-semantic OP Tab version");
        check(!(metadata.getVersion() instanceof SemanticVersion), "raw mod version remains raw");
        check(metadata.getEntrypoints("init").get(0).getValue().equals("io.github.betterclient.optab.OpTab"), "initializer remains metadata only");
        check(metadata.getDependencies().size() == 2, "no OP Tab dependency dropped");
        for (var dependency : metadata.getDependencies()) {
            check(dependency.getKind() == ModDependency.Kind.DEPENDS, "mandatory dependency preserved");
            switch (dependency.getModId()) {
                case "quilt_loader" -> {
                    check(dependency.matches(Version.parse("0.30.1")), "managed provider satisfies OP Tab");
                    check(!dependency.matches(Version.parse("0.15.9")), "OP Tab rejects older provider");
                }
                case "minecraft" -> {
                    check(dependency.matches(Version.parse("1.21.1")), "Minecraft 1.21.1 satisfies OP Tab");
                    check(!dependency.matches(Version.parse("1.20.6")), "OP Tab Minecraft requirement remains");
                }
                default -> throw new AssertionError("Unexpected OP Tab dependency " + dependency.getModId());
            }
        }
    }

    /** Optional pinned-binary differential audit. Neither a Quilt engine nor Minecraft is started. */
    public static void main(String[] args) throws Exception {
        run();
        if (args.length != 2) throw new IllegalArgumentException("Expected official Quilt 0.30.1 JAR and approved OP Tab JAR");
        Path upstream = Path.of(args[0]);
        check(sha256(Files.readAllBytes(upstream)).equals(QUILT_SHA256), "pinned official Quilt binary");
        Path actualFabric = Path.of(Version.class.getProtectionDomain().getCodeSource().getLocation().toURI());
        check(sha256(Files.readAllBytes(actualFabric)).equals(FFLOADER_SHA256), "actual pinned FFLoader binary");
        Path optab = Path.of(args[1]);
        check(sha256(Files.readAllBytes(optab)).equals(OPTAB_SHA256), "approved unchanged OP Tab archive");
        try (JarFile jar = new JarFile(optab.toFile()); InputStream input = jar.getInputStream(jar.getJarEntry("quilt.mod.json"))) {
            byte[] descriptor = input.readAllBytes();
            check(sha256(descriptor).equals(DESCRIPTOR_SHA256), "fixture is original archive descriptor");
            checkOptab(parse(descriptor));
        }
        // Quilt also includes Fabric API classes. Isolate it from the real FFLoader under test.
        try (var quilt = new URLClassLoader(new URL[] {upstream.toUri().toURL()}, ClassLoader.getPlatformClassLoader())) {
            var versionType = quilt.loadClass("org.quiltmc.loader.api.Version");
            var rangeType = quilt.loadClass("org.quiltmc.loader.api.VersionRange");
            var parse = quilt.loadClass("org.quiltmc.loader.impl.metadata.qmj.V1ModMetadataReader").getMethod("readVersionSpecifier", String.class);
            var versionOf = versionType.getMethod("of", String.class);
            var matches = rangeType.getMethod("isSatisfiedBy", versionType);
            int cases = 0;
            for (String bound : BOUNDS) for (String operator : OPERATORS) {
                String range = operator + bound;
                Object nativeRange = parse.invoke(null, range);
                var hostPredicate = VersionPredicate.parse(range);
                for (String version : VERSIONS) {
                    boolean nativeResult = (boolean) matches.invoke(nativeRange, versionOf.invoke(null, version));
                    check(nativeResult == hostPredicate.test(Version.parse(version)), "Quilt/FFLoader parity " + range + " vs " + version);
                    cases++;
                }
            }
            // Evidence for keeping the extension narrow: these must not be silently projected.
            Object bare = parse.invoke(null, "0.16.0-");
            check((boolean) matches.invoke(bare, versionOf.invoke(null, "0.16.1"))
                    && !VersionPredicate.parse("0.16.0-").test(Version.parse("0.16.1")), "bare constraint semantics diverge");
            Object raw = parse.invoke(null, ">=0.16.0-");
            check((boolean) matches.invoke(raw, versionOf.invoke(null, "2.0.0V1.21.1+1.21"))
                    && !VersionPredicate.parse(">=0.16.0-").test(Version.parse("2.0.0V1.21.1+1.21")), "raw candidate semantics diverge");
            System.out.println("NATIVE_QUILT_PRERELEASE_PARITY cases=" + cases + " assertions=" + assertions + " PASS");
        }
    }
}
