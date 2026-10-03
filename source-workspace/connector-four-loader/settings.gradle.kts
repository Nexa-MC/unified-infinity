pluginManagement {
    repositories {
        gradlePluginPortal()
        maven {
            name = "Su5eD"
            url = uri("https://maven.su5ed.dev/releases")
        }
    }

    plugins {
        id("org.gradle.toolchains.foojay-resolver-convention") version "0.8.0"
    }
}

rootProject.name = "connector"

include("transformer")
include(":infinity-core", ":infinity-fart")
project(":infinity-core").projectDir = file("components/infinity-core")
project(":infinity-fart").projectDir = file("components/infinity-fart")

include(":infinity-adapter")
project(":infinity-adapter").projectDir = file("components/infinity-adapter")


// Canonical full-source FML owns BOOT and the internal component contracts.
include(":fml-unified")
project(":fml-unified").projectDir = file("../fml-unified")
