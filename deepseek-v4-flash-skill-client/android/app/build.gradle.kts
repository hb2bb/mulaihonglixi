plugins { id("com.android.application"); id("com.chaquo.python") }
android {
    namespace = "app.qiyu.local"
    compileSdk = 35
    defaultConfig {
        applicationId = "app.qiyu.local"
        minSdk = 24
        targetSdk = 35
        versionCode = 2
        versionName = "0.1.1"
        ndk { abiFilters += listOf("arm64-v8a", "x86_64") }
    }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
}
chaquopy { defaultConfig { version = "3.11"; pyc { src = false } } }
val bundleRuntime by tasks.registering(Exec::class) {
    workingDir(rootProject.projectDir.parentFile)
    commandLine("python3", "android/scripts/bundle_runtime.py")
}
tasks.named("preBuild") { dependsOn(bundleRuntime) }
