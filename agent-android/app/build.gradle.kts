plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.devicekit.agent"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.devicekit.agent"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "1.0.0"

        buildConfigField("String", "DEVICEKIT_SERVER_URL", "\"http://127.0.0.1:7317\"")

        // plan 25 phase 3: pinned Ed25519 public key (hex) for verifying OTA update manifests.
        // Empty by default (dev builds skip signature verification but still enforce sha256).
        // Release builds should override this with the real publisher key.
        buildConfigField("String", "OTA_PUBLIC_KEY", "\"\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    // Two editions of the same app:
    //   full — the DeviceKit fleet agent (plus Faro remote-control support)
    //   faro — lean "Faro Agent": only the Faro daemon; no DeviceKit HTTP
    //          server/backend/accessibility/overlay (see src/full/AndroidManifest.xml
    //          for everything the faro edition deliberately leaves out)
    flavorDimensions += "edition"
    productFlavors {
        create("full") {
            dimension = "edition"
            resValue("string", "app_name", "DeviceKit Agent")
        }
        create("faro") {
            dimension = "edition"
            applicationId = "com.faro.agent"
            resValue("string", "app_name", "Faro Agent")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_1_8
        targetCompatibility = JavaVersion.VERSION_1_8
    }

    kotlinOptions {
        jvmTarget = "1.8"
    }

    buildFeatures {
        buildConfig = true
    }
}

dependencies {
    // Embedded Faro agent daemon (Rust via JNI) + Kotlin controller
    implementation(project(":faro-protocol"))

    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("com.google.android.material:material:1.11.0")

    // ViewPager2 + Fragments
    implementation("androidx.viewpager2:viewpager2:1.0.0")
    implementation("androidx.fragment:fragment-ktx:1.6.2")

    // HTTP client
    implementation("com.squareup.okhttp3:okhttp:4.12.0")

    // JSON
    implementation("org.json:json:20231013")

    // Embedded HTTP server (NanoHTTPD)
    implementation("org.nanohttpd:nanohttpd:2.3.1")

    // Coroutines
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")

    // Ed25519 signature verification for OTA update manifests (plan 25 phase 3)
    implementation("org.bouncycastle:bcprov-jdk15on:1.70")

    // Lifecycle
    implementation("androidx.lifecycle:lifecycle-service:2.7.0")
}
