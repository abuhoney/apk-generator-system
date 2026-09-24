"""
project_generator.py — Generates a complete Android project tree per function.

For each function folder, this produces a full Android project that wraps
the function's rendered template.html inside a WebView activity. The output
project can be compiled by `apk_builder.py` into a signed .apk.

Output tree (under _builds/<function>/):
    app/
      build.gradle
      src/main/
        AndroidManifest.xml
        java/com/bardom/generator/MainActivity.java
        assets/webapp/
          index.html          ← rendered template
          strings.json        ← copy of function's strings.json
          config.json         ← copy of function's config.json
          css/                ← function's CSS assets
          js/                 ← function's JS assets
          images/             ← function's image assets
        res/
          layout/activity_main.xml
          values/strings.xml
          values/colors.xml
          values/themes.xml
          mipmap-*/ic_launcher.png
    build.gradle              (project-level)
    settings.gradle
    gradle.properties
    local.properties
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional

from .config import get_config
from .function_registry import get_registry
from .template_renderer import render_template_file as render_function


# --------------------------------------------------------------------------- #
# Template strings
# --------------------------------------------------------------------------- #
PROJECT_GRADLE = """\
// Top-level build file
buildscript {
    repositories {
        google()
        mavenCentral()
    }
    dependencies {
        classpath 'com.android.tools.build:gradle:8.1.0'
    }
}
allprojects {
    repositories {
        google()
        mavenCentral()
    }
}
"""

SETTINGS_GRADLE = """\
rootProject.name = "{app_name}"
include ':app'
"""

GRADLE_PROPERTIES = """\
android.useAndroidX=true
android.enableJetifier=true
org.gradle.jvmargs=-Xmx2048m
"""

APP_GRADLE = """\
apply plugin: 'com.android.application'

android {{
    namespace '{package_name}'
    compileSdk {compile_sdk}

    defaultConfig {{
        applicationId "{package_name}"
        minSdk {min_sdk}
        targetSdk {target_sdk}
        versionCode {version_code}
        versionName "{version_name}"
    }}

    buildTypes {{
        release {{
            minifyEnabled false
        }}
    }}

    compileOptions {{
        sourceCompatibility JavaVersion.VERSION_17
        targetCompatibility JavaVersion.VERSION_17
    }}
}}

dependencies {{
    implementation 'androidx.appcompat:appcompat:1.6.1'
    implementation 'androidx.webkit:webkit:1.8.0'
}}
"""

ANDROID_MANIFEST = """\
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />

    <application
        android:allowBackup="true"
        android:icon="@mipmap/ic_launcher"
        android:label="@string/app_name"
        android:theme="@style/Theme.App"
        android:usesCleartextTraffic="true">

        <activity
            android:name=".MainActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
"""

MAIN_ACTIVITY_JAVA = """\
package {package_name};

import android.app.Activity;
import android.os.Bundle;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebSettings;

public class MainActivity extends Activity {{
    private WebView webView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {{
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        webView = findViewById(R.id.webview);
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        settings.setDatabaseEnabled(true);

        webView.setWebViewClient(new WebViewClient());
        // Load the bundled webapp
        webView.loadUrl("file:///android_asset/webapp/index.html");
    }}

    @Override
    public void onBackPressed() {{
        if (webView != null && webView.canGoBack()) {{
            webView.goBack();
        }} else {{
            super.onBackPressed();
        }}
    }}
}}
"""

ACTIVITY_MAIN_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<FrameLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="match_parent">
    <WebView
        android:id="@+id/webview"
        android:layout_width="match_parent"
        android:layout_height="match_parent" />
</FrameLayout>
"""

STRINGS_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">{app_name}</string>
</resources>
"""

COLORS_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="primary">#58a6ff</color>
    <color name="background">#0d1117</color>
    <color name="surface">#161b22</color>
</resources>
"""

THEMES_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <style name="Theme.App" parent="android:Theme.Material.NoActionBar">
        <item name="android:colorBackground">@color/background</item>
        <item name="android:statusBarColor">@color/background</item>
    </style>
</resources>
"""


# --------------------------------------------------------------------------- #
# Generator
# --------------------------------------------------------------------------- #
def _package_name_for(function_name: str) -> str:
    safe = "".join(c if c.isalnum() else "" for c in function_name.lower())
    return f"com.bardom.app.{safe or 'default'}"


def generate_function_project(function_name: str,
                               out_dir: Optional[Path] = None,
                               app_name: Optional[str] = None,
                               package_name: Optional[str] = None,
                               min_sdk: int = 24,
                               target_sdk: int = 34,
                               compile_sdk: int = 34,
                               version_code: int = 1,
                               version_name: str = "1.0.0") -> Path:
    """Generate a full Android project tree for the given function."""
    cfg = get_config()
    fm = get_registry().get(function_name)
    if fm is None:
        raise FileNotFoundError(f"Function not found: {function_name}")

    if out_dir is None:
        out_dir = cfg.build_dir / function_name
    out_dir.mkdir(parents=True, exist_ok=True)

    if app_name is None:
        app_name = fm.manifest.get("name", function_name.replace("_", " ").title())
    if package_name is None:
        package_name = fm.manifest.get("package", _package_name_for(function_name))

    pkg_path = package_name.replace(".", "/")
    java_dir = out_dir / "app" / "src" / "main" / "java" / pkg_path
    java_dir.mkdir(parents=True, exist_ok=True)

    # Render the function's template.html into assets/webapp/index.html
    try:
        rendered_html = render_function(fm.path)
    except Exception as e:
        rendered_html = f"<!-- render error: {e} --><h1>{app_name}</h1>"

    assets_dir = out_dir / "app" / "src" / "main" / "assets" / "webapp"
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / "index.html").write_text(rendered_html, encoding="utf-8")

    # Copy config.json + strings.json so the APK carries the full context
    for fname in ("config.json", "strings.json"):
        src = fm.path / fname
        if src.exists():
            shutil.copy2(src, assets_dir / fname)

    # Copy asset subfolders (css, js, images, data, assets)
    for sub in ("css", "js", "images", "data", "assets"):
        src_dir = fm.path / sub
        if src_dir.is_dir():
            shutil.copytree(src_dir, assets_dir / sub, dirs_exist_ok=True)

    # Java files
    (java_dir / "MainActivity.java").write_text(
        MAIN_ACTIVITY_JAVA.format(package_name=package_name), encoding="utf-8")

    # res
    res_dir = out_dir / "app" / "src" / "main" / "res"
    (res_dir / "layout").mkdir(parents=True, exist_ok=True)
    (res_dir / "values").mkdir(parents=True, exist_ok=True)
    (res_dir / "mipmap-hdpi").mkdir(parents=True, exist_ok=True)

    (res_dir / "layout" / "activity_main.xml").write_text(ACTIVITY_MAIN_XML, encoding="utf-8")
    (res_dir / "values" / "strings.xml").write_text(
        STRINGS_XML.format(app_name=app_name), encoding="utf-8")
    (res_dir / "values" / "colors.xml").write_text(COLORS_XML, encoding="utf-8")
    (res_dir / "values" / "themes.xml").write_text(THEMES_XML, encoding="utf-8")

    # Manifest
    (out_dir / "app" / "src" / "main" / "AndroidManifest.xml").write_text(
        ANDROID_MANIFEST, encoding="utf-8")

    # Gradle
    (out_dir / "app" / "build.gradle").write_text(
        APP_GRADLE.format(
            package_name=package_name,
            compile_sdk=compile_sdk,
            min_sdk=min_sdk,
            target_sdk=target_sdk,
            version_code=version_code,
            version_name=version_name,
        ), encoding="utf-8")
    (out_dir / "build.gradle").write_text(PROJECT_GRADLE, encoding="utf-8")
    (out_dir / "settings.gradle").write_text(
        SETTINGS_GRADLE.format(app_name=app_name), encoding="utf-8")
    (out_dir / "gradle.properties").write_text(GRADLE_PROPERTIES, encoding="utf-8")

    # local.properties — points at the Android SDK
    sdk_path = cfg.android_sdk_path or "/opt/android-sdk"
    (out_dir / "local.properties").write_text(
        f"sdk.dir={sdk_path}\n", encoding="utf-8")

    # manifest.json — build descriptor
    manifest = {
        "function": function_name,
        "app_name": app_name,
        "package": package_name,
        "min_sdk": min_sdk,
        "target_sdk": target_sdk,
        "compile_sdk": compile_sdk,
        "version_code": version_code,
        "version_name": version_name,
        "generated_at": str(__import__("datetime").datetime.utcnow()),
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")

    return out_dir


if __name__ == "__main__":
    import sys
    fn = sys.argv[1] if len(sys.argv) > 1 else "calculator"
    out = generate_function_project(fn)
    print(f"Project generated → {out}")
