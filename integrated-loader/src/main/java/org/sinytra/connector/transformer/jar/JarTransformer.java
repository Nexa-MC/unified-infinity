package org.sinytra.connector.transformer.jar;

import com.google.common.base.Stopwatch;
import com.mojang.datafixers.util.Pair;
import com.mojang.logging.LogUtils;
import cpw.mods.jarhandling.JarContents;
import cpw.mods.jarhandling.JarContentsBuilder;
import cpw.mods.jarhandling.JarMetadata;
import cpw.mods.modlauncher.serviceapi.ILaunchPluginService;
import reloc.net.minecraftforge.fart.api.ClassProvider;
import org.sinytra.connector.infinity.BoundedBatch;
import org.sinytra.connector.infinity.LoadingPolicy;
import org.sinytra.connector.infinity.LoadProgress;
import org.jetbrains.annotations.Nullable;
import org.sinytra.adapter.env.ctx.AuditTrail;
import org.sinytra.connector.transformer.TransformerEnvironment;
import org.sinytra.connector.transformer.transform.TransformProgressMeter;
import org.sinytra.connector.transformer.transform.TransformerUtil;
import org.slf4j.Logger;
import org.slf4j.Marker;
import org.slf4j.MarkerFactory;
import org.spongepowered.asm.mixin.transformer.ClassInfo;

import java.io.File;
import java.io.IOException;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.IdentityHashMap;
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.TimeUnit;

import static cpw.mods.modlauncher.api.LambdaExceptionUtils.uncheck;

public final class JarTransformer {
    public static final String SOURCE_NAMESPACE = "intermediary";
    public static final String OBF_NAMESPACE = "mojang";
    public static final Marker TRANSFORM_MARKER = MarkerFactory.getMarker("TRANSFORM");
    private static final Logger LOGGER = LogUtils.getLogger();

    private final TransformerEnvironment environment;

    public JarTransformer(TransformerEnvironment environment) {
        this.environment = environment;
    }

    public List<TransformedFabricModPath> transform(List<TransformableJar> jars, List<Path> libs) {
        Map<TransformableJar, TransformedFabricModPath> outputs = new IdentityHashMap<>();
        List<Path> inputLibs = new ArrayList<>(libs);
        List<TransformableJar> needTransforming = new ArrayList<>();
        int cached = 0;
        for (TransformableJar jar : jars) {
            if (jar.cacheFile().isUpToDate()) {
                outputs.put(jar, jar.toTransformedPath());
                cached++;
            } else {
                needTransforming.add(jar);
            }
            inputLibs.add(jar.input().toPath());
        }
        LoadProgress.transformUnits(jars.size(), cached);
        if (!needTransforming.isEmpty()) {
            List<TransformedFabricModPath> transformed = transformJars(needTransforming, inputLibs);
            for (int i = 0; i < needTransforming.size(); i++) {
                outputs.put(needTransforming.get(i), transformed.get(i));
            }
        }
        // Cache state must not reorder candidates selected by the existing dependency resolver.
        return jars.stream().map(outputs::get).toList();
    }

    public TransformableJar cacheTransformableJar(File input) throws IOException {
        String name = input.getName().split("\\.(?!.*\\.)")[0];
        Path output = this.environment.createCachedJarPath(name);

        FabricModFileMetadata metadata = FabricJarReader.readModMetadata(input, this.environment);
        FabricModPath path = new FabricModPath(output, metadata);
        TransformerUtil.CacheFile cacheFile = TransformerUtil.getCached(input.toPath(), output, this.environment.getJarCacheVersion());
        String moduleName = getModuleName(input.toPath());
        return new TransformableJar(input, path, cacheFile, moduleName);
    }

    private List<TransformedFabricModPath> transformJars(List<TransformableJar> paths, List<Path> libs) {
        Stopwatch stopwatch = Stopwatch.createStarted();
        TransformProgressMeter progress = this.environment.createProgressMeter("[Connector] Transforming Jars", paths.size());
        ClassProvider ownedClassProvider = null;
        Throwable pendingFailure = null;
        try {
            TransformProgressMeter initProgress = this.environment.createProgressMeter("[Connector] Initializing Transformer", 0);
            JarTransformInstance transformInstance;
            try {
                ClassProvider classProvider = this.environment.getRuntimeClassProvider(libs);
                ownedClassProvider = classProvider;
                ILaunchPluginService.ITransformerLoader loader = name -> classProvider.getClassBytes(name.replace('.', '/')).orElseThrow(() -> new ClassNotFoundException(name));
                this.environment.setGlobalBytecodeLoader(loader);
                transformInstance = new JarTransformInstance(this.environment, classProvider, libs);
            } finally {
                initProgress.complete();
            }
            LoadingPolicy policy = LoadingPolicy.current(paths.size());
            LOGGER.info(TRANSFORM_MARKER, "Unified Infinity transform budget: {} workers for {} uncached jars (CPU {}, heap {}, cap {})",
                policy.workers(), paths.size(), policy.cpuBudget(), policy.heapBudget(), policy.configuredCap());
            List<TransformedFabricModPath> results;
            try {
                results = BoundedBatch.map(paths, policy.workers(), Duration.ofHours(1), jar -> {
                    Pair<FabricModPath, AuditTrail> pair = jar.transform(transformInstance);
                    progress.increment();
                    LoadProgress.transformedOne();
                    return new TransformedFabricModPath(jar.input().toPath(), pair.getFirst(), pair.getSecond());
                });
            } catch (BoundedBatch.BatchException failure) {
                TransformableJar failed = paths.get(failure.inputIndex());
                throw this.environment.onTransformationError("Error transforming file " + failed.input().getName(), failure.getCause());
            } catch (TimeoutException failure) {
                throw this.environment.onTransformationError("Timed out waiting for jar remap", failure);
            }
            uncheck(() -> transformInstance.getBfu().saveGeneratedAdapterJar());
            transformInstance.saveAuditReport();
            stopwatch.stop();
            LOGGER.debug(TRANSFORM_MARKER, "Processed all jars in {} ms", stopwatch.elapsed(TimeUnit.MILLISECONDS));
            return results;
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            RuntimeException failure = this.environment.onTransformationError("Interrupted while transforming jars", interrupted);
            pendingFailure = failure;
            throw failure;
        } catch (RuntimeException | Error failure) {
            pendingFailure = failure;
            throw failure;
        } finally {
            try {
                cleanupEnvironment();
            } finally {
                try {
                    // This provider owns input-JAR handles, not borrowed host directories.
                    // Workers have drained, adapter/audit writes ended, and the callback is removed.
                    if (ownedClassProvider != null) ownedClassProvider.close();
                } catch (Throwable closeFailure) {
                    if (pendingFailure != null) pendingFailure.addSuppressed(closeFailure);
                    else throw this.environment.onTransformationError("Failed to close transform class provider", closeFailure);
                } finally {
                    progress.complete();
                }
            }
        }
    }

    @SuppressWarnings("unchecked")
    private void cleanupEnvironment() {
        this.environment.setGlobalBytecodeLoader(null);
        try {
            MethodHandles.Lookup lookup = MethodHandles.privateLookupIn(ClassInfo.class, MethodHandles.lookup());

            // Remove cached class infos, which might not be up-to-date
            VarHandle cacheField = lookup.findStaticVarHandle(ClassInfo.class, "cache", Map.class);
            Map<String, ClassInfo> cache = (Map<String, ClassInfo>) cacheField.get();
            cache.clear();

            VarHandle objectField = lookup.findStaticVarHandle(ClassInfo.class, "OBJECT", ClassInfo.class);
            ClassInfo object = (ClassInfo) objectField.get();

            cache.put("java/lang/Object", object);
        } catch (Throwable t) {
            LOGGER.error("Error cleaning up after jar transformation", t);
        }
    }

    @Nullable
    private static String getModuleName(Path path) {
        try(JarContents contents = new JarContentsBuilder().paths(path).build()) {
            JarMetadata metadata = JarMetadata.from(contents);
            return metadata.descriptor().name();
        } catch (IOException e) {
            LOGGER.error("Error reading jar contents from {}", path, e);
            return null;
        }
    }

    public record FabricModPath(Path path, FabricModFileMetadata metadata) {}

    public record TransformedFabricModPath(Path input, FabricModPath output, @Nullable AuditTrail auditTrail) {}

    public record TransformableJar(File input, FabricModPath modPath, TransformerUtil.CacheFile cacheFile, String moduleName) {
        public Pair<FabricModPath, AuditTrail> transform(JarTransformInstance transformInstance) throws IOException {
            Files.deleteIfExists(this.modPath.path);
            AuditTrail audit = transformInstance.transformJar(this.input, this.modPath.path, this.modPath.metadata());
            this.cacheFile.save();
            return Pair.of(this.modPath, audit);
        }

        public TransformedFabricModPath toTransformedPath() {
            return new TransformedFabricModPath(this.input.toPath(), this.modPath, null);
        }
    }
}
