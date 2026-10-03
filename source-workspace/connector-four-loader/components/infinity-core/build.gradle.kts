import java.security.MessageDigest
import groovy.json.JsonOutput
import org.gradle.api.artifacts.component.ModuleComponentIdentifier

plugins { `java-library` }
repositories { mavenCentral() }
java { toolchain.languageVersion.set(JavaLanguageVersion.of(21)); withSourcesJar() }
val generated = layout.buildDirectory.dir("generated/sources/infinity/java")
val generatedResources = layout.buildDirectory.dir("generated/resources/infinity")
val identityInputs = rootProject.fileTree(rootProject.projectDir) {
    include("**/*.java", "**/*.gradle.kts", "**/src/main/resources/**", "**/src/mod/resources/**", "gradle/libs.versions.toml", "gradle/infinity-upstream-pins.json")
    exclude("**/build/**", ".gradle/**")
}
// Sibling BOOT/FML sources change admission, ABI and transformation ownership.
// Stable relative paths also let the complete source archive verify this identity.
val loaderIdentityInputs = rootProject.files(
    rootProject.fileTree("../admission-bootstrap") {
        include("src/**", "*.gradle.kts", "*.gradle", "LICENSE*"); exclude("**/build/**")
    },
    rootProject.fileTree("../fml-unified") {
        include("src/**", "*.gradle", "*.gradle.kts", "provenance/**", "LICENSE*", "MODIFICATIONS.md"); exclude("**/build/**")
    }
)
val allIdentityInputs = identityInputs + loaderIdentityInputs
fun identityPath(input: java.io.File): String {
    val relative = input.relativeTo(rootProject.projectDir).invariantSeparatorsPath
    return if (relative.startsWith("../")) "loader-sources/" + relative.removePrefix("../") else relative
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
    inputs.files(allIdentityInputs)
    inputs.files(dependencyInputs)
    outputs.dir(generated)
    outputs.dir(generatedResources)
    doLast {
        val digest = MessageDigest.getInstance("SHA-256")
        allIdentityInputs.files.sortedBy { identityPath(it) }.forEach {
            digest.update(identityPath(it).toByteArray())
            digest.update(0.toByte()); digest.update(it.readBytes()); digest.update(0.toByte())
        }
        // All source components and every resolved external compile/runtime dependency affect one identity.
        val dependencies = dependencyInputs.get().flatMap { it.files }.distinct().sortedBy { it.name }
        dependencies.forEach { digest.update(it.name.toByteArray()); digest.update(0.toByte()); digest.update(it.readBytes()); digest.update(0.toByte()) }
        digest.update(System.getProperty("java.runtime.version").toByteArray())
        val hash = digest.digest().joinToString("") { "%02x".format(it) }
        fun sha(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
        val manifest = mapOf(
            "schema" to 2,
            "identity_sha256" to hash,
            "compiler_runtime" to System.getProperty("java.runtime.version"),
            "scope" to "Component Java/resources, sibling BOOT/FML source and provenance, build scripts, upstream pins and resolved external compile/runtime/shade dependency bytes",
            "sources" to allIdentityInputs.files.sortedBy { identityPath(it) }.map {
                mapOf("path" to identityPath(it), "sha256" to sha(it.readBytes()))
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

val admissionInventorySelfTest by tasks.registering(JavaExec::class) {
    dependsOn(tasks.testClasses)
    classpath = sourceSets.test.get().runtimeClasspath
    mainClass.set("org.sinytra.connector.infinity.inventory.AdmissionInventoryTest")
    maxHeapSize = "96m"
    jvmArgs("-XX:ActiveProcessorCount=1")
}
tasks.check { dependsOn(admissionInventorySelfTest) }

// Internal compile-only view; production runtime ownership belongs to FML BOOT.
dependencies { compileOnly(project(":fml-unified")); testImplementation(project(":fml-unified")) }

// Preserve source-declared license metadata independently from host presentation defaults.
dependencies {
    // These exact files are hash-verified by :fml-unified:verifyCompileInputs.
    // Use the existing pinned installation cache without repository-specific metadata.
    testRuntimeOnly(files(rootProject.file("../../run/client-dev/libraries/com/google/code/gson/gson/2.10.1/gson-2.10.1.jar")))
    testRuntimeOnly(files(rootProject.file("../../run/client-dev/libraries/com/electronwill/night-config/core/3.8.3/core-3.8.3.jar")))
    testRuntimeOnly(files(rootProject.file("../../run/client-dev/libraries/com/electronwill/night-config/toml/3.8.3/toml-3.8.3.jar")))
}
val admissionLicenseSelfTest by tasks.registering(JavaExec::class) {
    dependsOn(tasks.testClasses)
    classpath = sourceSets.test.get().runtimeClasspath
    mainClass.set("org.sinytra.connector.infinity.inventory.AdmissionMetadataLicenseTest")
    maxHeapSize = "96m"
    jvmArgs("-XX:ActiveProcessorCount=1")
    mustRunAfter(admissionInventorySelfTest)
}
tasks.check { dependsOn(admissionLicenseSelfTest) }
