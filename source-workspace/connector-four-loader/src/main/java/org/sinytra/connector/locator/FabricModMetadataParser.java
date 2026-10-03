package org.sinytra.connector.locator;

import com.electronwill.nightconfig.core.Config;
import com.mojang.logging.LogUtils;
import net.fabricmc.loader.api.metadata.ContactInformation;
import net.fabricmc.loader.api.metadata.CustomValue;
import net.fabricmc.loader.api.metadata.Person;
import net.neoforged.fml.loading.moddiscovery.ModFile;
import net.neoforged.fml.loading.moddiscovery.ModFileInfo;
import net.neoforged.fml.loading.moddiscovery.NightConfigWrapper;
import net.neoforged.neoforgespi.language.IConfigurable;
import net.neoforged.neoforgespi.language.IModFileInfo;
import net.neoforged.neoforgespi.locating.IModFile;
import org.sinytra.connector.util.ConnectorUtil;
import org.slf4j.Logger;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/**
 * Parses Fabric mod JSON metadata into TOML format at runtime.
 */
public final class FabricModMetadataParser {
    private static final String DEFAULT_LICENSE = "All Rights Reserved";
    // From ModInfo
    private static final Pattern VALID_VERSION = Pattern.compile("^\\d+.*");
    private static final Logger LOGGER = LogUtils.getLogger();

    /** Presentation only. The preserved original AST is read, never rewritten or reparsed from disk. */
    static String presentationCredits(String fabricCredits, CustomValue originalQuilt) {
        CustomValue contributors = objectMember(objectMember(objectMember(originalQuilt, "quilt_loader"), "metadata"), "contributors");
        if (contributors == null || contributors.getType() != CustomValue.CvType.OBJECT) return fabricCredits;
        List<String> lines = new ArrayList<>();
        if (!fabricCredits.isEmpty()) lines.add(fabricCredits);
        for (Map.Entry<String, CustomValue> contributor : contributors.getAsObject()) {
            String name = contributor.getKey();
            CustomValue value = contributor.getValue();
            if (name == null || name.isBlank() || value == null) continue;
            List<String> roles = new ArrayList<>();
            if (value.getType() == CustomValue.CvType.STRING) roles.add(value.getAsString());
            else if (value.getType() == CustomValue.CvType.ARRAY) {
                boolean valid = true;
                for (CustomValue role : value.getAsArray()) {
                    if (role == null || role.getType() != CustomValue.CvType.STRING) { valid = false; break; }
                    roles.add(role.getAsString());
                }
                if (!valid) continue;
            } else continue;
            // No translation, role inference, deduplication or promotion of Owner/Developer to Author.
            lines.add(roles.isEmpty() ? name : name + ": " + String.join(", ", roles));
        }
        return String.join("\n", lines);
    }

    private static CustomValue objectMember(CustomValue object, String key) {
        return object == null || object.getType() != CustomValue.CvType.OBJECT ? null : object.getAsObject().get(key);
    }

    public static IModFileInfo createForgeMetadata(IModFile modFile, ConnectorFabricModMetadata metadata, Collection<String> activeMixinConfigs, boolean lowCode) {
        String modid = metadata.getId();

        Config config = Config.inMemory();
        config.add("modLoader", lowCode ? "lowcodefml" : "javafml");
        config.add("loaderVersion", "[0, )");
        Collection<String> licenses = metadata.getLicense()
            .stream().map(String::trim).filter(l -> !l.isBlank())
            .toList();
        config.add("license", licenses.isEmpty() ? DEFAULT_LICENSE : String.join(", ", metadata.getLicense()));

        config.add("properties", Map.of(
            "metadata", metadata,
            ConnectorUtil.CONNECTOR_MARKER, true
        ));
        config.add(List.of("modproperties", modid), metadata.getCustomValues());

        Config modListConfig = config.createSubConfig();
        modListConfig.add("modId", modid);
        // Native Quilt's exact dependency versions must survive FML admission. Java 21's
        // module-version grammar accepts '+'; only host module IDs need independent normalization.
        String version = metadata.containsCustomValue("infinity:quilt_metadata")
            ? metadata.getVersion().getFriendlyString() : metadata.getNormalizedVersion();
        // Validate version string. If it's invalid, we'll let FML assign a default version instead
        if (VALID_VERSION.matcher(version).matches()) {
            modListConfig.add("version", version);
        } else {
            LOGGER.warn("Ignoring invalid version for mod {} in file {}", modid, modFile.getFilePath());
        }
        modListConfig.add("displayName", metadata.getName());
        modListConfig.add("description", metadata.getDescription());
        metadata.getIconPath(-1).ifPresent(icon -> modListConfig.add("logoFile", icon));

        ContactInformation contact = metadata.getContact();
        contact.get("homepage")
            .or(() -> contact.get("source"))
            .or(() -> Optional.of(contact.asMap())
                .filter(m -> !m.isEmpty())
                .map(m -> m.entrySet().iterator().next().getValue()))
            // Ensure string is valid url
            .filter(ConnectorUtil::isValidURL)
            .ifPresent(url -> {
                modListConfig.add("modUrl", url);
                modListConfig.add("displayURL", url);
            });

        contact.get("issues")
            .filter(ConnectorUtil::isValidURL)
            .ifPresent(url -> modListConfig.add("issueTrackerURL", url));

        modListConfig.add("authors", metadata.getAuthors().stream()
            .map(Person::getName)
            .collect(Collectors.joining(", ")));

        String fabricCredits = metadata.getContributors().stream()
            .map(Person::getName)
            .collect(Collectors.joining(", "));
        // Quilt contributors carry declared roles, not a Fabric author/contributor classification.
        // Preserve those exact roles in host presentation credits without changing either public metadata API.
        modListConfig.add("credits", presentationCredits(fabricCredits, metadata.getCustomValue("infinity:quilt_metadata")));

        config.add("mods", List.of(modListConfig));

        List<Config> mixins = activeMixinConfigs.stream()
            .map(str -> {
                Config mixinConfig = modListConfig.createSubConfig();
                mixinConfig.add("config", str);
                return mixinConfig;
            })
            .toList();
        if (!mixins.isEmpty()) {
            config.add("mixins", mixins);
        }

        switch (metadata.getEnvironment()) {
            case CLIENT -> config.add("displayTest", "IGNORE_ALL_VERSION");
            case SERVER -> config.add("displayTest", "IGNORE_SERVER_VERSION");
        }

        // NeoForge's update checker compat
        Optional.ofNullable(metadata.getCustomValues().get("forgeUpdateJSONURL"))
            .filter(va -> va.getType() == CustomValue.CvType.STRING)
            .map(CustomValue::getAsString)
            .filter(ConnectorUtil::isValidURL)
            .ifPresent(url -> modListConfig.add("updateJSONURL", url));

        IConfigurable configurable = new NightConfigWrapper(config);
        return new ModFileInfo((ModFile) modFile, configurable, f -> {
        }, List.of());
    }
}
