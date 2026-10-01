# ProGuard rules for Lumax Phone Wrapper
# WebView-based app — minimal obfuscation needed

# Keep JavaScript interface methods
-keepclassmembers class se.lumax.phone.MainActivity$LumaxNativeBridge {
    @android.webkit.JavascriptInterface <methods>;
}

# Keep WebView related classes
-keep class android.webkit.** { *; }
-dontwarn android.webkit.**

# Keep Kotlin coroutines
-keepnames class kotlinx.coroutines.internal.MainDispatcherFactory {}
-keepnames class kotlinx.coroutines.CoroutineExceptionHandler {}