# ====== ProGuard Rules — BardomPro Universal APK Generator v6.0.0 ======
# Anti-decompile: obfuscate + shrink + strip logs

#------ Strip Log.v/d/i in release (keep w/e for crash reports) ------
-assumenosideeffects class android.util.Log {
    public static *** v(...);
    public static *** d(...);
    public static *** i(...);
}

#------ Keep app core classes (but obfuscate internals) ------
-keep class com.bardom.universal.BardomApp { *; }
-keep class com.bardom.universal.MainActivity { *; }
-keep class com.bardom.universal.MainActivity$EngineBridge { *; }
-keepclassmembers class com.bardom.universal.MainActivity$EngineBridge {
    @android.webkit.JavascriptInterface <methods>;
}

#------ Keep network interfaces (needed for reflection) ------
-keep class com.bardom.universal.net.** { *; }
-keepclassmembers class com.bardom.universal.net.** { *; }

#------ Keep BuildConfig (secrets are there) ------
-keep class com.bardom.universal.BuildConfig { *; }

#------ Firebase / Gson / OkHttp ------
-keep class com.google.gson.** { *; }
-keepattributes Signature
-keepattributes *Annotation*
-keepclassmembers,allowobfuscation class * {
    @com.google.gson.annotations.* <fields>;
}
-dontwarn okhttp3.**
-dontwarn okio.**
-keep class okhttp3.** { *; }
-keep interface okhttp3.** { *; }

#------ WorkManager ------
-keep class androidx.work.** { *; }
-dontwarn androidx.work.**

#------ Enums ------
-keepclassmembers enum * {
    public static **[] values();
    public static ** valueOf(java.lang.String);
}

#------ Native methods ------
-keepclasseswithmembernames class * {
    native <methods>;
}

#------ Prevent re-signing detection from breaking ------
-keep class com.bardom.universal.SecurityShield { *; }

#------ Remove debug info ------
-renamesourcefileattribute SourceFile
-keepattributes SourceFile,LineNumberTable
