package org.sinytra.connector.locator;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import net.fabricmc.loader.api.metadata.CustomValue;
import net.fabricmc.loader.impl.metadata.*;
import org.sinytra.connector.transformer.quilt.NativeQuiltMetadata;

/** Tests the production parser's presentation helper using original metadata, not guessed identities. */
public final class QuiltContributorPresentationTest {
    private static int checks;
    private static Path temporary;
    private static void equal(Object expected, Object actual, String reason) {
        if (!Objects.equals(expected, actual)) throw new AssertionError(reason + ": expected=" + expected + ", actual=" + actual);
        checks++;
    }
    private static LoaderModMetadata nativeMetadata(String json) throws Exception {
        return NativeQuiltMetadata.parse(new ByteArrayInputStream(json.getBytes(StandardCharsets.UTF_8)),
            "/original/optab.jar", new VersionOverrides(), new DependencyOverrides(temporary), false);
    }
    private static CustomValue carrier(String originalQuilt) throws Exception {
        String fabric = "{\"schemaVersion\":1,\"id\":\"presentation_fixture\",\"version\":\"1.0.0\",\"custom\":{\"infinity:quilt_metadata\":" + originalQuilt + "}}";
        return ModMetadataParser.parseMetadata(new ByteArrayInputStream(fabric.getBytes(StandardCharsets.UTF_8)),
            "presentation fixture only", List.of(), new VersionOverrides(), new DependencyOverrides(temporary), false)
            .getCustomValue("infinity:quilt_metadata");
    }
    private static String project(String contributorObject) throws Exception {
        return FabricModMetadataParser.presentationCredits("", carrier("{\"quilt_loader\":{\"metadata\":{\"contributors\":" + contributorObject + "}}}"));
    }
    public static void main(String[] args) throws Exception {
        temporary = Files.createTempDirectory("quilt-credit-presentation-");
        try {
            Path fixture = Path.of(args[0]);
            String original = Files.readString(fixture, StandardCharsets.UTF_8);
            LoaderModMetadata metadata = nativeMetadata(original);
            CustomValue raw = metadata.getCustomValue(NativeQuiltMetadata.RAW_KEY);
            equal("BetterClient: Owner", FabricModMetadataParser.presentationCredits("", raw), "Exact original OP Tab owner attribution");
            equal("optab", metadata.getId(), "Original mod ID unchanged");
            equal("2.0.0V1.21.1+1.21", metadata.getVersion().getFriendlyString(), "Original Quilt version unchanged");
            equal(0, metadata.getAuthors().size(), "Contributor roles are not promoted into Fabric author identities");
            equal(0, metadata.getContributors().size(), "Public Fabric contributors remain untouched");
            equal("Owner", raw.getAsObject().get("quilt_loader").getAsObject().get("metadata").getAsObject()
                .get("contributors").getAsObject().get("BetterClient").getAsString(), "Original role AST remains intact");
            equal(original, Files.readString(fixture, StandardCharsets.UTF_8), "Original fixture bytes unchanged");
            equal("Existing contributor\nBetterClient: Owner", FabricModMetadataParser.presentationCredits("Existing contributor", raw), "Existing credits retained");
            equal("Alex: Developer, Translator\nBeta: Artist\nGamma", project("{\"Alex\":[\"Developer\",\"Translator\"],\"Beta\":\"Artist\",\"Gamma\":[]}"), "Multiple contributors and roles retain declaration order");
            equal("Alex: Maintainer, Maintainer", project("{\"Alex\":[\"Maintainer\",\"Maintainer\"]}"), "No role deduplication or reinterpretation");
            equal("Dev 名字: 开发者, Translation", project("{\"Dev 名字\":[\"开发者\",\"Translation\"]}"), "Unicode names/roles retained");
            equal("Valid: Artist", project("{\"Bad\":17,\"Mixed\":[\"Developer\",null],\"Valid\":\"Artist\",\" \":\"Owner\"}"), "Defensive malformed entries do not crash or invent attribution");
            for (String rawJson : List.of("null", "[]", "17", "{}", "{\"quilt_loader\":null}", "{\"quilt_loader\":{}}",
                    "{\"quilt_loader\":{\"metadata\":[]}}", "{\"quilt_loader\":{\"metadata\":{}}}",
                    "{\"quilt_loader\":{\"metadata\":{\"contributors\":[]}}}", "{\"quilt_loader\":{\"metadata\":{\"contributors\":17}}}")) {
                equal("Existing", FabricModMetadataParser.presentationCredits("Existing", carrier(rawJson)), "Missing/malformed original metadata preserves existing credits");
            }
            equal("Existing", FabricModMetadataParser.presentationCredits("Existing", null), "Ordinary Fabric credits unchanged");
            equal("", FabricModMetadataParser.presentationCredits("", null), "Absent contributors stay absent");
            LoaderModMetadata missing = nativeMetadata(original.replace("\"BetterClient\": \"Owner\"", ""));
            equal("", FabricModMetadataParser.presentationCredits("", missing.getCustomValue(NativeQuiltMetadata.RAW_KEY)), "Actual native parser accepts missing contributors without invention");
            for (String malformed : List.of("17", "[\"Owner\",null]", "{\"role\":\"Owner\"}")) {
                try {
                    nativeMetadata(original.replace("\"BetterClient\": \"Owner\"", "\"BetterClient\": " + malformed));
                    throw new AssertionError("Malformed original contributors admitted: " + malformed);
                } catch (IOException | ParseMetadataException expected) { checks++; }
            }
            System.out.println("PASS: " + checks + " original Quilt contributor presentation contracts");
        } finally {
            try (var files = Files.walk(temporary)) {
                for (Path path : files.sorted(Comparator.reverseOrder()).toList()) Files.delete(path);
            }
        }
    }
}
