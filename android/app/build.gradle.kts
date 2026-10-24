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
// The build number is the desktop's (fedtail/version.py): commits since the last release
// tag v*, and the commit — so one commit is one version everywhere: 0.19.0.dev212+gabc1234
// on the desktop and on the phone alike. CI checks out the whole history for it.
fun git(vararg args: String): String = try {
    val p = ProcessBuilder("git", *args).directory(repo).redirectErrorStream(true).start()
    val out = p.inputStream.bufferedReader().readText().trim()
    if (p.waitFor() == 0) out else ""
} catch (e: Exception) {
    ""
}
val commit: String = git("rev-parse", "--short", "HEAD")
val sinceTag: Int = git("describe", "--tags", "--long", "--match", "v[0-9]*")
    .takeIf { it.isNotEmpty() }?.split("-")?.let { it[it.size - 2].toIntOrNull() }
    ?: git("rev-list", "--count", "HEAD").toIntOrNull() ?: 0
val commitDate: String = git("log", "-1", "--format=%cs")
val release: String = fedtailVersion.substringBefore(".dev")
// as version.compose(): a dev version says how far past its tag, a release just itself
val shownVersion: String = when {
    commit.isEmpty() -> fedtailVersion
    ".dev" in fedtailVersion -> "$release.dev$sinceTag+g$commit"
    sinceTag == 0 -> release
    else -> "$release+$sinceTag.g$commit"
}
// Android's own number (installing over an older one needs a bigger one): the version's
// numbers, then the commits since its tag — 0.19.0.dev212 → 190 000 212
val buildNumber: Int = release.split(".").map { it.toIntOrNull() ?: 0 }.let { v ->
    ((v.getOrElse(0) { 0 } * 1000 + v.getOrElse(1) { 0 }) * 100 + v.getOrElse(2) { 0 }) * 100_000 +
        minOf(sinceTag, 99_999)
}

android {
    namespace = "online.dmesg.fedtail"
    compileSdk = 35

    defaultConfig {
        applicationId = "online.dmesg.fedtail"
        minSdk = 31 // Android 12: older is "necrophilia" (the author's word)
        targetSdk = 35
        versionCode = buildNumber
        versionName = shownVersion
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
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
        // the release key never enters the repository: CI writes it from its secrets
        // (ANDROID_KEYSTORE, base64) and gives the passwords as environment variables —
        // android/README.md, "Releases"
        System.getenv("FEDTAIL_KEYSTORE")?.takeIf { File(it).isFile }?.let { path ->
            create("release") {
                storeFile = File(path)
                storePassword = System.getenv("FEDTAIL_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("FEDTAIL_KEY_ALIAS")
                keyPassword = System.getenv("FEDTAIL_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        debug {
            signingConfig = signingConfigs.getByName("dev")
            // the dev build stands next to the released one, never replaces it
            applicationIdSuffix = ".dev"
        }
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.findByName("release")
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
    inputs.property("version", "$shownVersion $commitDate")
    doLast {
        // no git on a phone: version.py reads the build from here
        val shown = shownVersion
        corePython.get().file("fedtail/_build.py").asFile.writeText(
            "BUILD = \"$shown\"\nCOMMIT = \"$commit\"\nDATE = \"$commitDate\"\n")
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
    // pictures: avatars, previews, the viewer — straight from their servers, never with
    // the account's token (as the desktop's images.py); memory + disk cache of its own
    implementation("io.coil-kt:coil-compose:2.7.0")

    // UI tests on the emulator (src/androidTest): Compose's test rule over the real app
    androidTestImplementation(compose)
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test:core-ktx:1.6.1")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
}
