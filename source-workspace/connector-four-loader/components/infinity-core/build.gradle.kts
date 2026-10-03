import java.security.MessageDigest
import groovy.json.JsonOutput
import org.gradle.api.artifacts.component.ModuleComponentIdentifier

plugins { `java-library` }
java { toolchain.languageVersion.set(JavaLanguageVersion.of(21)); withSourcesJar() }
val generated = layout.buildDirectory.dir("generated/sources/infinity/java")
val generatedResources = layout.buildDirectory.dir("generated/resources/infinity")
val identityInputs = rootProject.fileTree(rootProject.projectDir) {
    include("**/*.java", "**/*.gradle.kts", "gradle/libs.versions.toml", "gradle/infinity-upstream-pins.json")
    exclude("**/build/**", ".gradle/**")
}
// Resolve only external module artifacts: never create a task cycle through our own output JARs.
val dependencyInputs = providers.provider {
    listOf(rootProject, project(":transformer"), project(":infinity-adapter"), project(":infinity-fart"))
        .flatMap { owner -> listOf("compileClasspath", "runtimeClasspath", "shade").mapNotNull { name ->
            owner.configurations.findByName(name)?.takeIf { it.isCanBeResolved }?.incoming?.artifactView {
                componentFilter { it is ModuleComponentIdentifier }
            }?.files
        }}
}
val generateBuildIdentity by tasks.registering {
    inputs.files(identityInputs)
    inputs.files(dependencyInputs)
    outputs.dir(generated)
    outputs.dir(generatedResources)
    doLast {
        val digest = MessageDigest.getInstance("SHA-256")
        identityInputs.files.sortedBy { it.relativeTo(rootProject.projectDir).invariantSeparatorsPath }.forEach {
            digest.update(it.relativeTo(rootProject.projectDir).invariantSeparatorsPath.toByteArray())
            digest.update(0.toByte()); digest.update(it.readBytes()); digest.update(0.toByte())
        }
        // All source components and every resolved external compile/runtime dependency affect one identity.
        val dependencies = dependencyInputs.get().flatMap { it.files }.distinct().sortedBy { it.name }
        dependencies.forEach { digest.update(it.name.toByteArray()); digest.update(0.toByte()); digest.update(it.readBytes()); digest.update(0.toByte()) }
        digest.update(System.getProperty("java.runtime.version").toByteArray())
        val hash = digest.digest().joinToString("") { "%02x".format(it) }
        fun sha(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
        val manifest = mapOf(
            "schema" to 1,
            "identity_sha256" to hash,
            "compiler_runtime" to System.getProperty("java.runtime.version"),
            "scope" to "All compiled component Java sources, build scripts, upstream pins and resolved external compile/runtime/shade dependency bytes",
            "sources" to identityInputs.files.sortedBy { it.relativeTo(rootProject.projectDir).invariantSeparatorsPath }.map {
                mapOf("path" to it.relativeTo(rootProject.projectDir).invariantSeparatorsPath, "sha256" to sha(it.readBytes()))
            },
            "dependencies" to dependencies.map { mapOf("filename" to it.name, "sha256" to sha(it.readBytes())) }
        )
        val metadata = generatedResources.get().file("META-INF/unified-infinity/build-identity.json").asFile
        metadata.parentFile.mkdirs()
        metadata.writeText(JsonOutput.prettyPrint(JsonOutput.toJson(manifest)) + "\n")
        val output = generated.get().file("org/sinytra/connector/infinity/BuildIdentity.java").asFile
        output.parentFile.mkdirs()
        output.writeText("package org.sinytra.connector.infinity;\npublic final class BuildIdentity {\nprivate BuildIdentity() {}\npublic static final String SOURCE_SHA256 = \"$hash\";\npublic static final String TRANSFORM_CACHE_SUFFIX = \":unified-infinity-full-source:$hash\";\n}\n")
    }
}
sourceSets.main { java.srcDir(generated); resources.srcDir(generatedResources) }
tasks.processResources { dependsOn(generateBuildIdentity) }
tasks.compileJava { dependsOn(generateBuildIdentity); options.release.set(21) }
val coreSelfTest by tasks.registering(JavaExec::class) {
    dependsOn(tasks.testClasses)
    classpath = sourceSets.test.get().runtimeClasspath
    mainClass.set("org.sinytra.connector.infinity.LoadingCoreTest")
    maxHeapSize = "256m"
}
tasks.check { dependsOn(coreSelfTest) }
