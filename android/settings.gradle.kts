// fedtail for Android: the Gradle project. The Python core is the repository's own
// fedtail/ package, copied in at build time (app/build.gradle.kts) — never a fork of it.
pluginManagement {
    repositories {
        gradlePluginPortal()
        google()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "fedtail"
include(":app")
