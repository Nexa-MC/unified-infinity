#!/usr/bin/env python3
import hashlib,json,pathlib
base=pathlib.Path(__file__).resolve().parent;t=base/'connector-combined'
pins={'schema':1,'minecraft':'1.21.1','java_major':21,'connector_commit':'8b27f1ad042aae8037bcc522b321c03fcce1a12a','adapter_core_sources_sha256':'7fe14fb8f5c4a737ac5e7e8d9c563b698f3341fc2a58c9074d4d3f2b08e9f4f8','fart_sources_sha256':'1cf3acb13c14360805a84040266cb12ad467bdd98238b3ba8ec1b115be79782a','adapter_patch_sha256':hashlib.sha256((base.parent/'lithium-trial/patches/final/adapter-source.patch').read_bytes()).hexdigest(),'adapter_userdev_snapshot':json.loads((base/'provenance/adapter-userdev-snapshot.json').read_text()),'artifact_kind':'research-source-build'}
(t/'gradle/infinity-upstream-pins.json').write_text(json.dumps(pins,indent=2,sort_keys=True)+'\n')
p=t/'components/infinity-core/build.gradle.kts';s=p.read_text().replace('import java.security.MessageDigest','import java.security.MessageDigest\nimport groovy.json.JsonOutput')
s=s.replace('val generated = layout.buildDirectory.dir("generated/sources/infinity/java")','val generated = layout.buildDirectory.dir("generated/sources/infinity/java")\nval generatedResources = layout.buildDirectory.dir("generated/resources/infinity")')
s=s.replace('"gradle/libs.versions.toml")','"gradle/libs.versions.toml", "gradle/infinity-upstream-pins.json")')
s=s.replace('outputs.dir(generated)','outputs.dir(generated)\n    outputs.dir(generatedResources)')
s=s.replace('val hash = digest.digest().joinToString("") { "%02x".format(it) }','''val hash = digest.digest().joinToString("") { "%02x".format(it) }
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
        metadata.writeText(JsonOutput.prettyPrint(JsonOutput.toJson(manifest)) + "\\n")''')
s=s.replace('sourceSets.main { java.srcDir(generated) }','sourceSets.main { java.srcDir(generated); resources.srcDir(generatedResources) }\ntasks.processResources { dependsOn(generateBuildIdentity) }')
p.write_text(s)
p=t/'build.gradle.kts';s=p.read_text()+'''
val infinityCompleteSources by tasks.registering(Zip::class) {
    archiveFileName.set("unified-infinity-complete-connector-fart-adapter-sources.zip")
    destinationDirectory.set(layout.buildDirectory.dir("distributions"))
    from(projectDir) {
        include("src/**", "transformer/src/**", "components/**/src/**", "**/*.gradle.kts",
            "gradle/libs.versions.toml", "gradle/infinity-upstream-pins.json", "LICENSE")
        exclude("**/build/**", "**/.gradle/**")
    }
}
tasks.named("fullJar") { dependsOn(infinityCompleteSources) }
''';p.write_text(s)
