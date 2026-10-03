package org.sinytra.connector.forge.loader;

import java.lang.annotation.ElementType;
import java.util.Collection;
import java.util.HashSet;
import java.util.Set;
import net.neoforged.fml.ModContainer;
import net.neoforged.fml.ModLoadingException;
import net.neoforged.fml.ModLoadingIssue;
import net.neoforged.neoforgespi.IIssueReporting;
import net.neoforged.neoforgespi.language.IModInfo;
import net.neoforged.neoforgespi.language.IModLanguageLoader;
import net.neoforged.neoforgespi.language.ModFileScanData;
import net.neoforged.neoforgespi.locating.IModFile;

/** A distinct adapter language, not another provider competing for javafml. */
public final class ForgeModLanguageLoader implements IModLanguageLoader {
    public static final String NAME = "unified_forge_52";
    public static final String VERSION = "1.0.0";

    @Override
    public String name() {
        return NAME;
    }

    @Override
    public String version() {
        return VERSION;
    }

    @Override
    public ModContainer loadMod(IModInfo info, ModFileScanData scan, ModuleLayer layer) {
        var entrypoints = scan.getAnnotatedBy(ForgeMod.class, ElementType.TYPE)
            .filter(annotation -> info.getModId().equals(annotation.annotationData().get("value")))
            .map(annotation -> annotation.clazz().getClassName())
            .sorted()
            .toList();
        if (entrypoints.size() != 1) {
            var cause = new IllegalArgumentException("Forge 52 adapter requires exactly one @Mod entrypoint for "
                + info.getModId() + "; found " + entrypoints);
            throw new ModLoadingException(ModLoadingIssue.error("fml.modloadingissue.failedtoloadmodclass")
                .withAffectedMod(info).withCause(cause));
        }
        return new ForgeModContainer(info, entrypoints.getFirst(), layer);
    }

    @Override
    public void validate(IModFile file, Collection<ModContainer> loadedContainers, IIssueReporting reporter) {
        Set<String> ownedModIds = new HashSet<>();
        for (var info : file.getModInfos()) {
            if (info.getLoader() == this) {
                ownedModIds.add(info.getModId());
            }
        }
        file.getScanResult().getAnnotatedBy(ForgeMod.class, ElementType.TYPE)
            .filter(annotation -> !ownedModIds.contains(annotation.annotationData().get("value")))
            .forEach(annotation -> reporter.addIssue(ModLoadingIssue.error(
                "fml.modloadingissue.javafml.dangling_entrypoint",
                annotation.annotationData().get("value"), annotation.clazz().getClassName(), file.getFilePath())
                .withAffectedModFile(file)));
    }
}
