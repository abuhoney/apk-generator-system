# Keep WebView + JS bridge
-keep class com.bardom.generator.** { *; }
-keep class * extends android.webkit.WebViewClient
-keep class * extends android.webkit.WebChromeClient
-keepattributes *Annotation*
