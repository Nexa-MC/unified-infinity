package org.sinytra.connector.infinity.inventory;

import cpw.mods.niofs.union.UnionFileSystem;
import cpw.mods.jarhandling.JarContents;
import cpw.mods.jarhandling.JarMetadata;
import java.util.Collection;
import java.util.HashSet;
import net.neoforged.jarjar.nio.pathfs.PathFileSystem;
import java.io.IOException;
import java.net.URI;
import java.nio.file.Path;

/** Authoritative backing-file identity for installed components, never general resource-path rewriting. */
public final class ArchiveOrigins {
    private ArchiveOrigins() {}
    public static Path physical(URI uri) throws IOException {
        Path path=Path.of(uri);
        for(int depth=0;depth<16;depth++) {
            if(path.getFileSystem() instanceof UnionFileSystem union) {
                if(!path.equals(union.getRoot()))
                    throw new IOException("Installed component has a grouped or non-root union origin");
                path=union.getPrimaryPath();
            } else if(path.getFileSystem() instanceof PathFileSystem nested) {
                if(!path.equals(nested.getPath("/"))) throw new IOException("Installed component has a non-root nested origin");
                path=nested.getTarget();
            } else return path.toRealPath();
        }
        throw new IOException("Installed component origin wrapper depth exceeded");
    }
    /** BootstrapLauncher groups equal module names; prove uniqueness from the sealed complete input set. */
    public static void requireUniqueModule(String moduleName, Path expected, Collection<Path> sealedInputs) throws IOException {
        var matches=new HashSet<Path>();
        for(Path input:new HashSet<>(sealedInputs)) {
            try(var contents=JarContents.of(input)) {
                if(JarMetadata.from(contents).name().equals(moduleName))matches.add(input.toRealPath());
            }
        }
        if(!matches.equals(java.util.Set.of(expected.toRealPath())))
            throw new IOException("Installed BOOT module does not have exactly one sealed backing archive");
    }
    /** Narrow lookup by actual declared package; package membership is not an admission grant. */
    public static Module componentModule(ModuleLayer layer, Path expected, String className) throws IOException {
        String packageName = className.substring(0, className.lastIndexOf('.'));
        Path pinned = expected.toRealPath();
        Module owner = null;
        for (Module module : layer.modules()) {
            // Empty virtual libraries have no component package and no physical archive to inspect.
            if (!module.getPackages().contains(packageName)) continue;
            var reference = layer.configuration().findModule(module.getName()).orElseThrow().reference();
            var location = reference.location().orElseThrow(() -> new IOException("Component package owner lacks an origin"));
            if (!physical(location).equals(pinned)) throw new IOException("Component package owner differs from the installed origin");
            if (owner != null) throw new IOException("More than one module owns the installed component package");
            owner = module;
        }
        if (owner == null) throw new IOException("Installed component is absent from the expected layer");
        return owner;
    }
    public static Path ofClass(Class<?> type) throws IOException {
        try {
            var source=type.getProtectionDomain().getCodeSource();
            if(source==null)throw new IOException("Installed component lacks code source");
            return physical(source.getLocation().toURI());
        } catch(java.net.URISyntaxException failure) {throw new IOException("Invalid installed component code source URI",failure);}
    }
}
