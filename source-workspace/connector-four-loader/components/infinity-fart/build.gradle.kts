plugins { `java-library` }
group = "org.sinytra"
version = "1.0.14-infinity"
java { toolchain.languageVersion.set(JavaLanguageVersion.of(21)); withSourcesJar() }
repositories { mavenCentral(); maven("https://maven.neoforged.net/releases") }
dependencies {
    compileOnly("org.jetbrains:annotations:13.0")
    api("net.minecraftforge:srgutils:0.5.1")
    implementation("net.sf.jopt-simple:jopt-simple:6.0-alpha-3")
    implementation("org.ow2.asm:asm:9.5")
    implementation("org.ow2.asm:asm-commons:9.5")
    implementation("org.ow2.asm:asm-tree:9.5")
    testImplementation(project(":infinity-core"))
}
tasks.withType<JavaCompile>().configureEach { options.release.set(21) }
val directEntrySelfTest by tasks.registering(JavaExec::class) {
    dependsOn(tasks.testClasses)
    classpath = sourceSets.test.get().runtimeClasspath
    mainClass.set("net.minecraftforge.fart.internal.DirectEntryTest")
    maxHeapSize = "256m"
}
tasks.check { dependsOn(directEntrySelfTest) }
