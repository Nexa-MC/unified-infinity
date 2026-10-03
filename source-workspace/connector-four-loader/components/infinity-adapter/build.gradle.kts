plugins { `java-library` }
group = "org.sinytra.adapter"
version = "2.0.43+1.21.1-infinity"
java { toolchain.languageVersion.set(JavaLanguageVersion.of(21)); withSourcesJar() }
repositories {
    mavenCentral()
    maven("https://maven.fabricmc.net")
    maven("https://libraries.minecraft.net")
}
dependencies {
    compileOnly("org.jetbrains:annotations:24.0.1")
    api("com.mojang:datafixerupper:8.0.16")
    api(platform("org.ow2.asm:asm-bom:9.8"))
    listOf("asm", "asm-commons", "asm-tree", "asm-analysis", "asm-util").forEach { api("org.ow2.asm:$it") }
    implementation("com.mojang:logging:1.1.1")
    implementation("com.google.guava:guava:32.1.2-jre")
    implementation("org.slf4j:slf4j-api:2.0.0")
    implementation("net.fabricmc:sponge-mixin:0.14.0+mixin.0.8.6")
    implementation("io.github.llamalad7:mixinextras-common:0.3.1")
}
tasks.withType<JavaCompile>().configureEach { options.release.set(21); options.compilerArgs.add("-proc:none") }
