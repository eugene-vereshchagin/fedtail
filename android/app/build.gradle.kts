// The app: Kotlin + Jetpack Compose screens over fedtail's Python core (Chaquopy).
//
// The core is not copied by hand into this folder: `copyFedtail` takes the repository's
// fedtail/ package at build time (without the desktop's Qt, GTK, terminal and web
// interfaces), so the phone always runs the same core as the desktop of that commit.
// docs: android/README.md.

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("com.chaquo.python")
}

val repo: File = rootDir.parentFile

// fedtail/__init__.py says the version being worked towards (0.19.0.dev0)
val fedtailVersion: String = Regex("""__version__\s*=\s*"([^"]+)"""")
    .find(repo.resolve("fedtail/__init__.py").readText())!!.groupValues[1]
// grows with every CI build; 1 on a desk
val buildNumber: Int = (System.getenv("GITHUB_RUN_NUMBER") ?: "1").toInt()
val commit: String = (System.getenv("GITHUB_SHA") ?: "").take(7)

android {
    namespace = "online.dmesg.fedtail"
    compileSdk = 35

    defaultConfig {
        applicationId = "online.dmesg.fedtail"
        minSdk = 31 // Android 12: older is "necrophilia" (the author's word)
        targetSdk = 35
        versionCode = buildNumber
        versionName = fedtailVersion
        ndk {
            // phones, and the emulator; nothing else is worth the megabytes
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }

    signingConfigs {
        // dev builds share one key, so each new one installs over the last. It is in the
        // repository on purpose and signs nothing but online.dmesg.fedtail.dev; a release
        // gets its own key, kept out of here (docs: the porting plan, "keys").
        create("dev") {
            storeFile = rootProject.file("dev.keystore")
            storePassword = "fedtail-dev"
            keyAlias = "dev"
            keyPassword = "fedtail-dev"
        }
    }

    buildTypes {
        debug {
            signingConfig = signingConfigs.getByName("dev")
            // the dev build stands next to the released one, never replaces it
            applicationIdSuffix = ".dev"
            versionNameSuffix = "-dev"
        }
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
}

val corePython = layout.buildDirectory.dir("fedtail-python")

val copyFedtail = tasks.register<Sync>("copyFedtail") {
    description = "The repository's fedtail core, as the phone needs it"
    from(repo.resolve("fedtail")) {
        into("fedtail")
        exclude("**/__pycache__/**", "_build.py")
        // the desktop's windows stay home; the web interface's JSON layer and the
        // terminal's plain model come along: the app's bridge stands on them
        exclude("frontends/qt/**", "frontends/gtk/**")
        exclude("frontends/tui/app.py", "frontends/tui/screens.py", "frontends/tui/host.py",
                "frontends/tui/pictures.py")
        exclude("data/web/**")
    }
    // the made-up world of fedtail's screenshots: the dev build's demo mode (CI's emulator)
    from(repo.resolve("tests")) {
        into("tests")
        include("__init__.py", "fakes.py")
    }
    from(repo.resolve("tools")) {
        into("tools")
        include("showcase.py")
    }
    into(corePython)
    inputs.property("version", "$fedtailVersion $buildNumber $commit")
    doLast {
        // no git on a phone: version.py reads the build from here
        val shown = if (commit.isEmpty()) fedtailVersion else "$fedtailVersion+$buildNumber.g$commit"
        corePython.get().file("fedtail/_build.py").asFile.writeText(
            "BUILD = \"$shown\"\nCOMMIT = \"$commit\"\nDATE = \"\"\n")
    }
}

tasks.named("preBuild") { dependsOn(copyFedtail) }
// Chaquopy's own tasks read the copy: they wait for it (mergeDebugPythonSources & co.)
tasks.matching { it.name != copyFedtail.name && it.name.contains("Python") }
    .configureEach { dependsOn(copyFedtail) }

chaquopy {
    defaultConfig {
        version = "3.12"
        System.getenv("CHAQUOPY_BUILD_PYTHON")?.let { buildPython(it) }
        pip {
            install("requests")
            install("cryptography") // sync's AES-GCM (core/sync/crypto.py)
        }
    }
    sourceSets {
        getByName("main") {
            srcDir("src/main/python")
            srcDir(corePython.get().asFile)
        }
    }
}

dependencies {
    val compose = platform("androidx.compose:compose-bom:2024.10.01")
    implementation(compose)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
}
