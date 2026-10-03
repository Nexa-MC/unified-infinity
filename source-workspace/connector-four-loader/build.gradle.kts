import java.security.MessageDigest
import com.github.jengelman.gradle.plugins.shadow.tasks.ShadowJar
import me.modmuss50.mpp.ReleaseType
import net.neoforged.moddevgradle.dsl.RunModel
import net.neoforged.moddevgradle.internal.RunGameTask

plugins {
    java
    `maven-publish`
    alias(libs.plugins.moddevgradle)
    alias(libs.plugins.shadow) apply false
    alias(libs.plugins.modPublishPlugin)
    alias(libs.plugins.gradleutils)
    alias(libs.plugins.adapterUserdev)
    alias(libs.plugins.wikiToolkit)
}

val versionConnector: String by project
val versionMc = libs.versions.minecraft.get()
val curseForgeId: String by project
val modrinthId: String by project
val githubRepository: String by project
val publishBranch: String by project
val forgifiedFabricApiCurseForge: String by project
val forgifiedFabricApiModrinth: String by project
val connectorExtrasCurseForge: String by project
val connectorExtrasModrinth: String by project

val PUBLISH_RELEASE_TYPE: Provider<String> = providers.environmentVariable("PUBLISH_RELEASE_TYPE")

group = "org.sinytra"
version = "$versionConnector+$versionMc+infinity-source"
// Append git commit hash for dev versions
if (!PUBLISH_RELEASE_TYPE.isPresent) {
    version = "$version+dev-${gradleutils.gitInfo["hash"]}"
}
logger.lifecycle("Project version: $version")

val mod: SourceSet by sourceSets.creating

val shade: Configuration by configurations.creating

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(21))
    withSourcesJar()
}

configurations {
    compileOnly {
        extendsFrom(shade)
    }

    "modCompileOnly" {
        extendsFrom(shade)
    }
}

println("Java: ${System.getProperty("java.version")}, JVM: ${System.getProperty("java.vm.version")} (${System.getProperty("java.vendor")}), Arch: ${System.getProperty("os.arch")}")
neoForge {
    // Specify the version of NeoForge to use.
    version = libs.versions.neoforge.get()

    accessTransformers {
        from(project.file("src/mod/resources/META-INF/accesstransformer.cfg"))
    }

    parchment {
        mappingsVersion = libs.versions.parchment.get()
        minecraftVersion = libs.versions.parchmentMc.get()
    }

    runs {
        configureEach {
            additionalRuntimeClasspathConfiguration.extendsFrom(shade)
            additionalRuntimeClasspathConfiguration.dependencies.add(dependencies.create(files(tasks.jar)))
        }

        val config = Action<RunModel> {
            systemProperty("forge.logging.console.level", "debug")
            systemProperty("forge.logging.markers", "REGISTRIES,SCAN,FMLHANDSHAKE,COREMOD")
            systemProperty("connector.logging.markers", "MIXINPATCH,MERGER")
            systemProperty("mixin.debug.export", "true")
            gameDirectory.set(layout.projectDirectory.dir("run"))
        }

        create("client") {
            client()
            config(this)
        }

        create("server") {
            server()
            config(this)
        }
    }

    addModdingDependenciesTo(mod)

    mods {
        maybeCreate("connector").apply {
            sourceSet(mod)
        }
    }
}

repositories {
    maven {
        name = "Sinytra"
        url = uri("https://maven.su5ed.dev/releases")
        content {
            includeGroupAndSubgroups("org.sinytra")
        }
    }
    maven {
        name = "Fabric"
        url = uri("https://maven.fabricmc.net")
    }
    maven {
        url = uri("https://www.cursemaven.com")
        content {
            includeGroup("curse.maven")
        }
    }
    mavenLocal()
}

dependencies {
    shade(libs.forgifiedFabricLoader)
    shade(libs.classTweaker) { isTransitive = false }
    shade(libs.forgeAutoRenamingTool) { isTransitive = false }
    shade(libs.adapterCore) { isTransitive = false }
    shade(project(":transformer")) { isTransitive = false }

    val adapterRuntime = dependencies.create(libs.adapterRuntime.get())
    jarJar(adapterRuntime)
    implementation(adapterRuntime)

    val forgifiedFabricApi = (dependencies.create(libs.forgifiedFabricApi.get()) as ExternalModuleDependency).apply {
        exclude(group = "org.sinytra", module = "forgified-fabric-loader")
    }
    implementation(forgifiedFabricApi)
    "modImplementation"(forgifiedFabricApi)

    "modCompileOnly"(sourceSets.main.get().output)

//    implementation("curse.maven:connector-extras-913445:5618470")
}

val modJar: Jar by tasks.creating(Jar::class) {
    from(mod.output)
    manifest.attributes("Implementation-Version" to project.version)
    archiveClassifier.set("mod")
}
localJarJar("modJarConfig", "org.sinytra:connector-mod", project.version.toString(), modJar)

val depsJar: ShadowJar by tasks.creating(ShadowJar::class) {
    configurations = listOf(shade)

    exclude(
        "assets/fabricloader/**",
        "META-INF/*.SF", "META-INF/*.RSA",
        "META-INF/maven/**", "META-INF/jars/**", "META-INF/jarjar/**"
    )
    exclude("META-INF/services/net.neoforged.neoforgespi.language.IModLanguageLoader")
    exclude("ui/**")
    exclude("*.json", "*.html", "*.version")
    exclude("module-info.class")
    exclude("LICENSE.txt")

    dependencies {
        exclude(dependency("org.ow2.asm:"))
        exclude(dependency("net.sf.jopt-simple:"))
        exclude(dependency("com.google.guava:guava"))
        exclude(dependency("com.google.code.gson:gson"))
    }

    archiveClassifier.set("deps")
}

val fullJar by tasks.registering(ShadowJar::class) {
    from(
        depsJar.archiveFile.map(::zipTree),
        tasks.jar.flatMap { it.archiveFile.map(::zipTree) })
    mergeServiceFiles() // Relocate services
    relocate("net.minecraftforge.fart", "reloc.net.minecraftforge.fart")
    relocate("net.minecraftforge.srgutils", "reloc.net.minecraftforge.srgutils")
    relocate("net.fabricmc.classtweaker", "reloc.net.fabricmc.classtweaker")
    relocate("org.sat4j", "reloc.org.sat4j")
    relocate("net.bytebuddy", "reloc.net.bytebuddy")
    manifest.attributes(tasks.jar.get().manifest.attributes)
    archiveClassifier.set("full")

    doLast {
        val githubOutput = System.getenv("GITHUB_OUTPUT")
        if (githubOutput != null) {
            File(githubOutput).appendText("PRIMARY_ARTIFACT=${archiveFile.get().asFile.absolutePath}")
        }
    }
}

tasks {
    jar {
        manifest {
            attributes(
                "Specification-Title" to project.name,
                "Specification-Vendor" to "Sinytra",
                "Specification-Version" to "1",
                "Implementation-Title" to project.name,
                "Implementation-Version" to project.version,
                "Implementation-Vendor" to "Sinytra",
                "Automatic-Module-Name" to "org.sinytra.connector",
                "Fabric-Loader-Version" to libs.versions.forgifiedFabricLoader.get().split("+")[1]
            )
        }
    }
    withType<JavaCompile> {
        options.encoding = "UTF-8"
    }
    assemble {
        dependsOn(fullJar)
    }
    withType<RunGameTask> {
        dependsOn(jar)
    }
}

val versionPattern = "(?<ver>[\\d.]+)-?(?<channel>beta)?\\.?(?<mod>\\d+)?\\+?(?<game>[\\d.]+)?(?:\\+(?<dev>dev)?-?(?<hash>.+)?)?".toRegex()

publishMods {
    file.set(fullJar.flatMap { it.archiveFile })
    changelog.set(providers.environmentVariable("CHANGELOG").orElse("# $version"))
    type.set(PUBLISH_RELEASE_TYPE.orElse("alpha").map(ReleaseType::of))
    modLoaders.add("neoforge")
    dryRun.set(!providers.environmentVariable("CI").isPresent)
    displayName.set(version.map { s ->
        val matched = versionPattern.matchEntire(s) ?: throw IllegalArgumentException("Unexpected version format")
        val mainVer = matched.groups["ver"]?.value ?: throw IllegalArgumentException("Missing main version")
        val channelVer = matched.groups["channel"]?.value?.let { it + (matched.groups["mod"]?.value?.let { m -> " $m" } ?: "") } ?: ""
        val devHash = matched.groups["hash"]?.value?.let { "(dev $it)" } ?: ""
        "Connector $mainVer" + (if (channelVer.isNotEmpty()) " $channelVer" else "") + (if (devHash.isNotEmpty()) " $devHash" else "")
    })

    github {
        accessToken.set(providers.environmentVariable("GITHUB_TOKEN"))
        repository.set(githubRepository)
        commitish.set(publishBranch)
    }
    curseforge {
        accessToken.set(providers.environmentVariable("CURSEFORGE_TOKEN"))
        projectId.set(curseForgeId)
        minecraftVersions.add(versionMc)
        client.set(true)
        server.set(true)
        requires {
            slug.set(forgifiedFabricApiCurseForge)
        }
        optional {
            slug.set(connectorExtrasCurseForge)
        }
    }
    modrinth {
        accessToken.set(providers.environmentVariable("MODRINTH_TOKEN"))
        projectId.set(modrinthId)
        minecraftVersions.add(versionMc)
        requires {
            id.set(forgifiedFabricApiModrinth)
        }
        optional {
            id.set(connectorExtrasModrinth)
        }
    }
}

configurations.runtimeElements {
    setExtendsFrom(emptySet())
    outgoing {
        artifacts.clear()
        artifact(fullJar)
    }
}

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            suppressAllPomMetadataWarnings()

            from(components["java"])
        }
    }

    repositories {
        val env = System.getenv()
        if (env["MAVEN_URL"] != null) {
            repositories.maven {
                url = uri(env["MAVEN_URL"] as String)
                if (env["MAVEN_USERNAME"] != null) {
                    credentials {
                        username = env["MAVEN_USERNAME"]
                        password = env["MAVEN_PASSWORD"]
                    }
                }
            }
        }
    }
}

wiki {
    docs {
        create("connector") {
            root = file("docs")
        }
    }
}

fun localJarJar(configName: String, mavenCoords: String, version: String, artifact: Any) {
    configurations.create(configName) {
        attributes {
            attribute(Usage.USAGE_ATTRIBUTE, project.objects.named(Usage.JAVA_RUNTIME))
        }
        outgoing {
            artifact(artifact)
            capability("$mavenCoords:$version")
        }
    }
    dependencies {
        jarJar(project(":")) { capabilities { requireCapability(mavenCoords) } }
    }
}

// Unified Infinity: one compiled core, one FART implementation, one existing host SPI.
sourceSets.main {
    java.srcDirs("components/infinity-host-neoforge/src/main/java", "components/infinity-mc-1.21.1/src/main/java")
}
dependencies { shade(project(":infinity-core")) { isTransitive = false } }
allprojects {
    configurations.configureEach {
        resolutionStrategy.dependencySubstitution {
            substitute(module("org.sinytra:ForgeAutoRenamingTool")).using(project(":infinity-fart"))
            substitute(module("org.sinytra.adapter:core")).using(project(":infinity-adapter"))
        }
    }
    tasks.withType<AbstractArchiveTask>().configureEach {
        isPreserveFileTimestamps = false
        isReproducibleFileOrder = true
    }
}
tasks.named<ShadowJar>("fullJar") {
    dependsOn(":infinity-core:check", ":infinity-fart:check", ":infinity-fart:sourcesJar")
    from(project(":infinity-fart").layout.buildDirectory.file("libs/infinity-fart-1.0.14-infinity-sources.jar")) {
        into("META-INF/unified-infinity/sources")
    }
    manifest.attributes("Unified-Infinity-Build" to "complete-connector-and-fart-source-research")
}

tasks.named<ShadowJar>("fullJar") {
    dependsOn(":infinity-adapter:sourcesJar")
    from(project(":infinity-adapter").layout.buildDirectory.file("libs/infinity-adapter-2.0.43+1.21.1-infinity-sources.jar")) {
        into("META-INF/unified-infinity/sources")
    }
    manifest.attributes("Unified-Infinity-Build" to "complete-connector-fart-adapter-source-research")
}

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

// Compile-only ABI of the exact managed QSL base. Runtime is the original pinned module via host discovery.
val nativeQuiltBase = layout.projectDirectory.file("../../docs/four-loader/quilt/upstream/qsl_base-alpha5.jar")
dependencies { "modCompileOnly"(files(nativeQuiltBase)) }

// Bounded Forge 52.1 ABI facade; host reader/language provider and game APIs remain in their host layers.
sourceSets.main { java.srcDir("components/infinity-forge/src/main/java") }
sourceSets.named("mod") { java.srcDir("components/infinity-forge/src/mod/java") }

val verifyNativeQuiltInputs by tasks.registering {
    val pins = mapOf(
        "qsl_base-alpha5.jar" to "7eb4ec613f901ef7232f9f84ee91be5576f00682f32ad9c9f7b1a679bcf82465",
        "lifecycle_events-alpha5.jar" to "1a1f9b72c38e2475b471df1dcff7992d6ae4955e8a2cd8288bb3ba3986768aa4"
    )
    inputs.files(pins.keys.map { file("../../docs/four-loader/quilt/upstream/$it") })
    doLast {
        pins.forEach { (name, expected) ->
            val actual = MessageDigest.getInstance("SHA-256").digest(file("../../docs/four-loader/quilt/upstream/$name").readBytes()).joinToString("") { "%02x".format(it) }
            check(actual == expected) { "Pinned native QSL dependency mismatch: $name" }
        }
    }
}
tasks.named("compileModJava") { dependsOn(verifyNativeQuiltInputs) }

val nativeQuiltApiRegression by tasks.registering(Exec::class) {
    commandLine("bash", "four-loader/api-tests/run.sh")
    workingDir(projectDir)
}
tasks.check { dependsOn(nativeQuiltApiRegression, ":transformer:nativeQuiltRegression") }
tasks.named<Zip>("infinityCompleteSources") {
    from(projectDir) { include("four-loader/api-tests/**"); exclude("**/classes/**", "**/test-classes/**") }
}

val forgeAdapterRegression by tasks.registering(Exec::class) {
    dependsOn(tasks.classes)
    commandLine("bash", "components/infinity-forge/run-adapter-tests.sh")
    workingDir(projectDir)
}
val forgeFacadeRegression by tasks.registering(Exec::class) {
    dependsOn("compileModJava")
    commandLine("bash", "components/infinity-forge/run-facade-tests.sh")
    workingDir(projectDir)
}
tasks.check { dependsOn(forgeAdapterRegression, forgeFacadeRegression) }

val forgeEventRegression by tasks.registering(Exec::class) {
    dependsOn("compileModJava")
    commandLine("bash", "components/infinity-forge/run-event-tests.sh")
    workingDir(projectDir)
}
val forgeClumpsRegression by tasks.registering(Exec::class) {
    dependsOn(tasks.classes)
    commandLine("bash", "components/infinity-forge/run-clumps-tests.sh")
    workingDir(projectDir)
}
tasks.check { dependsOn(forgeEventRegression, forgeClumpsRegression) }
