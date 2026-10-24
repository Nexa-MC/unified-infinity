// SPDX-License-Identifier: MIT
import java.nio.file.*;
import java.util.*;
import org.quiltmc.loader.impl.lib.tinyremapper.*;
/** Compile input derivation only. Uses the original locked Quilt Loader's TinyRemapper.
 * No class is loaded/initialized from Minecraft; resources/signatures are intentionally not copied.
 * Mapping conflicts are NOT ignored. Output is never represented as a runnable game archive.
 */
public final class RemapServer {
    public static void main(String[] args) throws Exception {
        if (args.length != 4) throw new IllegalArgumentException("mapping input output libraries");
        Path mapping = Path.of(args[0]);
        if (!Files.readAllLines(mapping).get(0).equals("v1\tofficial\tintermediary\tmojang")) throw new IllegalStateException("namespaces");
        if (Files.exists(Path.of(args[2]))) throw new IllegalStateException("output exists");
        var remapper = TinyRemapper.newRemapper().withMappings(TinyUtils.createTinyMappingProvider(mapping, "official", "intermediary"))
            .threads(1).ignoreConflicts(false).build();
        try (var output = new OutputConsumerPath.Builder(Path.of(args[2])).build()) {
            var libraries = Files.readAllLines(Path.of(args[3])).stream().map(Path::of).toArray(Path[]::new);
            remapper.readClassPath(libraries);
            remapper.readInputs(Path.of(args[1]));
            remapper.apply(output);
        } finally { remapper.finish(); }
        System.out.println("NATIVE_TINYREMAPPER_OFFICIAL_TO_INTERMEDIARY_COMPILE_CLASSES_ONLY PASS");
    }
}
