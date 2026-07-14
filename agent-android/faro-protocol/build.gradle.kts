plugins {
    id("com.android.library")
    id("org.jetbrains.kotlin.android")
}

// The Faro agent daemon is Rust (reused from the Faro repo via the crate in
// rust/); cargo-ndk cross-compiles it into jniLibs for these ABIs. Requires
// `cargo install cargo-ndk` + the rustup Android targets + an NDK discoverable
// via ANDROID_NDK_HOME or the SDK's ndk/ dir.
val cargoAbis = listOf("arm64-v8a", "armeabi-v7a", "x86_64")
val rustJniLibs = layout.buildDirectory.dir("rustJniLibs")

val cargoNdkBuild = tasks.register<Exec>("cargoNdkBuild") {
    workingDir = file("rust")
    inputs.files(fileTree("rust/src"), "rust/Cargo.toml", "rust/Cargo.lock")
    outputs.dir(rustJniLibs)
    // 16 KB page alignment is mandatory on Android 15+ devices.
    environment("RUSTFLAGS", "-Clink-arg=-Wl,-z,max-page-size=16384")
    commandLine(
        "cargo", "ndk",
        *cargoAbis.flatMap { listOf("-t", it) }.toTypedArray(),
        "--platform", "26",
        "-o", rustJniLibs.get().asFile.absolutePath,
        "build", "--release",
    )
}

android {
    namespace = "com.faro.protocol"
    compileSdk = 34

    defaultConfig {
        minSdk = 26
    }

    sourceSets["main"].jniLibs.srcDir(rustJniLibs)

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_1_8
        targetCompatibility = JavaVersion.VERSION_1_8
    }

    kotlinOptions {
        jvmTarget = "1.8"
    }
}

tasks.named("preBuild") {
    dependsOn(cargoNdkBuild)
}

dependencies {
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("org.json:json:20231013")
}
