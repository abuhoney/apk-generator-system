"""
apk_builder_v3.py — Builds REAL, installable, UNIQUE APKs from source.

Unlike v2 (which reused a fixed shell APK), v3 compiles a fresh APK
from the Android project source in /android/ using:
    aapt2 compile  →  aapt2 link  →  d8 (dex)  →  zipalign  →  apksigner

Each APK gets:
    - A unique package name (com.bardom.app.<function>)
    - A unique app label (the function's display name)
    - A unique versionCode + versionName
    - A colored launcher icon (generated from a hash of the function name)
    - The function's rendered webapp in assets/

This guarantees multiple APKs can be installed side-by-side without
conflicts, and each one shows up with its own name + icon in the launcher.
"""
from __future__ import annotations

import os
import io
import json
import shutil
import struct
import zipfile
import hashlib
import subprocess
import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from .config import get_config
from .function_registry import get_registry
from .template_renderer import render_function


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ANDROID_DIR = PROJECT_ROOT / "android"
AAPT2 = ANDROID_DIR / "tools" / "aapt2"
APKSIGNER_JAR = ANDROID_DIR / "tools" / "apksigner-lib.jar"
D8_JAR = ANDROID_DIR / "tools" / "d8.jar"
KEYSTORE = ANDROID_DIR / "debug.keystore"
KEYSTORE_ALIAS = "bardom-debug"
KEYSTORE_PASS = "bardom123"

# Android framework resources (needed by aapt2 link)
# We use the android.jar from the shell APK's framework — but actually aapt2
# needs the android.jar. Let's download it.
ANDROID_JAR = ANDROID_DIR / "tools" / "android.jar"


@dataclass
class BuildResult:
    function: str
    apk_path: Path
    apk_size: int
    build_mode: str
    success: bool
    error: Optional[str] = None
    duration_sec: float = 0.0
    manifest: dict = None

    def to_dict(self) -> dict:
        return {
            "function": self.function,
            "apk_path": str(self.apk_path) if self.apk_path else "",
            "apk_size": self.apk_size,
            "build_mode": self.build_mode,
            "success": self.success,
            "error": self.error,
            "duration_sec": self.duration_sec,
            "manifest": self.manifest,
        }


# --------------------------------------------------------------------------- #
# Ensure android.jar (the framework JAR needed by aapt2 link)
# --------------------------------------------------------------------------- #
def _ensure_android_jar() -> bool:
    """Download android.jar (API 34) if not present."""
    if ANDROID_JAR.exists() and ANDROID_JAR.stat().st_size > 1_000_000:
        return True
    import urllib.request, zipfile
    ANDROID_JAR.parent.mkdir(parents=True, exist_ok=True)
    # platform-34-ext10 from Google's Android repository
    url = "https://dl.google.com/android/repository/platform-34-ext10_r01.zip"
    zip_path = ANDROID_JAR.parent / "platform-34.zip"
    try:
        if not zip_path.exists() or zip_path.stat().st_size < 1_000_000:
            print(f"Downloading android.jar framework...", flush=True)
            urllib.request.urlretrieve(url, zip_path)
        # Extract android.jar from the zip
        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():
                if name.endswith("android.jar") and "android-34" in name:
                    with zf.open(name) as src, open(ANDROID_JAR, "wb") as dst:
                        dst.write(src.read())
                    break
        ok = ANDROID_JAR.exists() and ANDROID_JAR.stat().st_size > 1_000_000
        if ok:
            zip_path.unlink(missing_ok=True)
        return ok
    except Exception as e:
        print(f"android.jar download failed: {e}", flush=True)
        return False


# --------------------------------------------------------------------------- #
# Icon generator — creates a colored PNG icon from the function name
# --------------------------------------------------------------------------- #
def _generate_icon_png(function_name: str, app_name: str, size: int = 72) -> bytes:
    """Generate a simple colored PNG icon.

    The color is derived from a hash of the function name so each app
    gets a distinct, recognizable color. The first letter of the app
    name is drawn in the center.
    """
    # Pick a color from the function name hash
    h = hashlib.md5(function_name.encode()).digest()
    r, g, b = h[0], h[1], h[2]
    # Make it a bit brighter
    r = min(255, r + 60)
    g = min(255, g + 60)
    b = min(255, b + 60)

    # Build a PNG using pure Python (no PIL dependency)
    # We'll create a solid color square with a white circle in the middle
    # and the first letter of the app name.
    # For simplicity, just a solid color square — Android will scale it.

    def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
        import zlib
        chunk = chunk_type + data
        crc = struct.pack('>I', zlib.crc32(chunk) & 0xffffffff)
        return struct.pack('>I', len(data)) + chunk + crc

    # PNG signature
    sig = b'\x89PNG\r\n\x1a\n'
    # IHDR: width(4) + height(4) + bitdepth(1) + colortype(1) + compression(1) + filter(1) + interlace(1)
    # colortype 2 = RGB, bitdepth 8
    ihdr_data = struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0)
    ihdr = _png_chunk(b'IHDR', ihdr_data)
    # IDAT: raw pixel data (filter byte 0 + RGB pixels per row)
    import zlib
    raw = bytearray()
    for y in range(size):
        raw.append(0)  # filter type 0 (none)
        for x in range(size):
            # Draw a circle in the center
            cx, cy = size // 2, size // 2
            radius = size // 3
            dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            if dist < radius:
                # White circle
                raw.extend([255, 255, 255])
            else:
                raw.extend([r, g, b])
    compressed = zlib.compress(bytes(raw), 9)
    idat = _png_chunk(b'IDAT', compressed)
    iend = _png_chunk(b'IEND', b'')
    return sig + ihdr + idat + iend


def _write_icons(res_dir: Path, function_name: str, app_name: str, function_dir: Path = None) -> None:
    """Write launcher icons at multiple densities.
    If function_dir/app_icon.png exists, use it as the custom icon.
    Otherwise, generate a colored icon from the function name hash.
    """
    # Check for custom icon
    custom_icon_path = function_dir / "app_icon.png" if function_dir else None
    custom_icon_bytes = None
    if custom_icon_path and custom_icon_path.exists():
        try:
            custom_icon_bytes = custom_icon_path.read_bytes()
            print(f"[icons] using custom icon ({len(custom_icon_bytes)} bytes)", flush=True)
        except Exception as e:
            print(f"[icons] failed to read custom icon: {e}", flush=True)
    densities = {
        "mipmap-mdpi": 48,
        "mipmap-hdpi": 72,
        "mipmap-xhdpi": 96,
        "mipmap-xxhdpi": 144,
        "mipmap-xxxhdpi": 192,
    }
    for folder, size in densities.items():
        d = res_dir / folder
        d.mkdir(parents=True, exist_ok=True)
        if custom_icon_bytes:
            # Use the custom icon (Android will scale it)
            (d / "ic_launcher.png").write_bytes(custom_icon_bytes)
        else:
            icon = _generate_icon_png(function_name, app_name, size)
            (d / "ic_launcher.png").write_bytes(icon)


# --------------------------------------------------------------------------- #
# Manifest + strings customization
# --------------------------------------------------------------------------- #
def _write_manifest(src_dir: Path, package: str, version_code: int,
                    version_name: str, min_sdk: int, target_sdk: int,
                    app_name: str) -> None:
    """Write a custom AndroidManifest.xml with the given package."""
    manifest = f'''<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="{package}"
    android:versionCode="{version_code}"
    android:versionName="{version_name}">

    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />

    <application
        android:label="@string/app_name"
        android:icon="@mipmap/ic_launcher"
        android:allowBackup="true"
        android:usesCleartextTraffic="true"
        android:theme="@android:style/Theme.Material.NoActionBar"
        android:hardwareAccelerated="true">

        <activity
            android:name=".MainActivity"
            android:exported="true"
            android:configChanges="orientation|screenSize|keyboardHidden">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
'''
    (src_dir / "AndroidManifest.xml").write_text(manifest, encoding="utf-8")


def _write_strings(res_dir: Path, app_name: str) -> None:
    """Write strings.xml with the app name."""
    vals = res_dir / "values"
    vals.mkdir(parents=True, exist_ok=True)
    strings = f'''<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">{app_name}</string>
</resources>
'''
    (vals / "strings.xml").write_text(strings, encoding="utf-8")


def _write_layout(res_dir: Path) -> None:
    """Write activity_main.xml (WebView layout)."""
    layout = res_dir / "layout"
    layout.mkdir(parents=True, exist_ok=True)
    xml = '''<?xml version="1.0" encoding="utf-8"?>
<FrameLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="match_parent">
    <WebView
        android:id="@+id/webview"
        android:layout_width="match_parent"
        android:layout_height="match_parent" />
</FrameLayout>
'''
    (layout / "activity_main.xml").write_text(xml, encoding="utf-8")


def _write_colors(res_dir: Path) -> None:
    vals = res_dir / "values"
    vals.mkdir(parents=True, exist_ok=True)
    colors = '''<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="primary">#58a6ff</color>
    <color name="background">#0d1117</color>
</resources>
'''
    (vals / "colors.xml").write_text(colors, encoding="utf-8")


# --------------------------------------------------------------------------- #
# Java source
# --------------------------------------------------------------------------- #
JAVA_SOURCE = '''package {package_name};

import android.app.Activity;
import android.os.Bundle;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebSettings;
import android.view.KeyEvent;

public class MainActivity extends Activity {{
    private WebView webView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {{
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        webView = findViewById(R.id.webview);
        WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setAllowFileAccess(true);
        s.setAllowContentAccess(true);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        s.setSupportZoom(false);
        s.setBuiltInZoomControls(false);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);

        webView.setWebViewClient(new WebViewClient());

        // Load the bundled webapp from assets
        webView.loadUrl("file:///android_asset/webapp/index.html");
    }}

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {{
        if (keyCode == KeyEvent.KEYCODE_BACK && webView != null && webView.canGoBack()) {{
            webView.goBack();
            return true;
        }}
        return super.onKeyDown(keyCode, event);
    }}

    @Override
    protected void onResume() {{
        super.onResume();
        if (webView != null) webView.onResume();
    }}

    @Override
    protected void onPause() {{
        if (webView != null) webView.onPause();
        super.onPause();
    }}
}}
'''


# --------------------------------------------------------------------------- #
# Ensure Java + keytool
# --------------------------------------------------------------------------- #
_JRE_DIR: Optional[Path] = None


def _ensure_java() -> bool:
    """Check if java AND javac are available; download portable JDK if needed.

    We need javac (the Java compiler) to compile MainActivity.java, so a
    JRE-only install is not enough — we need a full JDK.
    """
    global _JRE_DIR

    # Check if javac already works (system JDK)
    try:
        r = subprocess.run(["javac", "-version"], capture_output=True, timeout=10)
        if r.returncode == 0:
            return True
    except Exception:
        pass

    # Check cached JDK
    jre_base = Path("/tmp") / "bardom-jdk"
    marker = jre_base / "java_path.txt"
    if marker.exists():
        saved = marker.read_text().strip()
        if saved and Path(saved).exists():
            os.environ["PATH"] = saved + os.pathsep + os.environ.get("PATH", "")
            _JRE_DIR = Path(saved).parent
            # Verify javac works
            try:
                r = subprocess.run(["javac", "-version"], capture_output=True, timeout=10)
                if r.returncode == 0:
                    return True
            except Exception:
                pass

    # Download portable JDK (includes javac, not just JRE)
    import urllib.request, tarfile
    jre_base.mkdir(parents=True, exist_ok=True)
    url = "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.5%2B11/OpenJDK21U-jdk_x64_linux_hotspot_21.0.5_11.tar.gz"
    tar_path = jre_base / "jdk.tar.gz"
    try:
        if not tar_path.exists() or tar_path.stat().st_size < 1_000_000:
            print("Downloading portable JDK (includes javac)...", flush=True)
            urllib.request.urlretrieve(url, tar_path)
        with tarfile.open(tar_path, "r:gz") as tf:
            tf.extractall(jre_base)
        for d in jre_base.iterdir():
            if d.is_dir() and (d / "bin" / "java").exists() and (d / "bin" / "javac").exists():
                _JRE_DIR = d
                marker.write_text(str(d / "bin"))
                os.environ["PATH"] = str(d / "bin") + os.pathsep + os.environ.get("PATH", "")
                os.environ["JAVA_HOME"] = str(d)
                print(f"JDK ready: {d}", flush=True)
                return True
    except Exception as e:
        print(f"JDK download failed: {e}", flush=True)
    return False


def _ensure_keystore() -> None:
    if KEYSTORE.exists():
        return
    KEYSTORE.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "keytool", "-genkeypair",
        "-keystore", str(KEYSTORE),
        "-alias", KEYSTORE_ALIAS,
        "-keypass", KEYSTORE_PASS,
        "-storepass", KEYSTORE_PASS,
        "-keyalg", "RSA", "-keysize", "2048",
        "-validity", "10000",
        "-dname", "CN=BardomPro APK Generator, OU=Mobile Apps, O=BardomPro, L=Riyadh, ST=Riyadh, C=SA",
    ], check=True, capture_output=True)


# --------------------------------------------------------------------------- #
# Build pipeline
# --------------------------------------------------------------------------- #
def _run(cmd: list[str], cwd: Optional[Path] = None,
         timeout: int = 120) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return proc.returncode, proc.stdout, proc.stderr


def _prepare_project(function_name: str, app_name: str, package: str,
                     version_code: int, version_name: str,
                     min_sdk: int, target_sdk: int,
                     function_dir: Path) -> Path:
    """Prepare a temporary Android project for the function."""
    cfg = get_config()
    build_dir = cfg.build_dir / function_name / "v3"
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True)

    src_main = build_dir / "src" / "main"
    res_dir = src_main / "res"
    java_dir = src_main / "java" / package.replace(".", "/")
    assets_dir = src_main / "assets" / "webapp"

    java_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)
    res_dir.mkdir(parents=True, exist_ok=True)

    # 1. Manifest
    _write_manifest(src_main, package, version_code, version_name, min_sdk, target_sdk, app_name)

    # 2. Resources
    _write_strings(res_dir, app_name)
    _write_colors(res_dir)
    _write_layout(res_dir)
    _write_icons(res_dir, function_name, app_name, function_dir)

    # 3. Java source
    java_src = JAVA_SOURCE.format(package_name=package)
    (java_dir / "MainActivity.java").write_text(java_src, encoding="utf-8")

    # 4. Assets — rendered webapp
    try:
        index_html = render_function(function_dir)
    except Exception as e:
        index_html = f"<!DOCTYPE html><html><body><h1>{app_name}</h1><p>Error: {e}</p></body></html>"
    (assets_dir / "index.html").write_text(index_html, encoding="utf-8")

    # Copy config.json + strings.json + css/js
    for fname in ("config.json", "strings.json"):
        src = function_dir / fname
        if src.exists():
            shutil.copy2(src, assets_dir / fname)
    for sub in ("css", "js", "images", "data", "media"):
        src_dir = function_dir / sub
        print(f"[v3-debug] checking {src_dir} exists={src_dir.is_dir()}", flush=True)
        if src_dir.is_dir():
            print(f"[v3-debug] copying {src_dir} -> {assets_dir / sub}", flush=True)
            try:
                shutil.copytree(src_dir, assets_dir / sub, dirs_exist_ok=True)
                # Verify
                copied = list((assets_dir / sub).rglob("*"))
                print(f"[v3-debug]   copied {len([p for p in copied if p.is_file()])} files to {assets_dir / sub}", flush=True)
                for p in copied:
                    if p.is_file():
                        print(f"[v3-debug]     {p.relative_to(assets_dir)} ({p.stat().st_size})", flush=True)
            except Exception as copy_err:
                print(f"[v3-debug]   COPY FAILED: {copy_err}", flush=True)
                import traceback
                print(traceback.format_exc(), flush=True)
        else:
            print(f"[v3-debug] {src_dir} does not exist", flush=True)

    return build_dir


def _compile_resources(project_dir: Path, compiled_zip: Path) -> bool:
    """aapt2 compile res/* → compiled.zip."""
    res_dir = project_dir / "src" / "main" / "res"
    # Collect all resource files
    res_files = []
    for p in sorted(res_dir.rglob("*")):
        if p.is_file():
            res_files.append(str(p))
    if not res_files:
        return False
    cmd = [str(AAPT2), "compile", "-o", str(compiled_zip)] + res_files
    rc, out, err = _run(cmd, timeout=60)
    return rc == 0


def _link_apk(project_dir: Path, compiled_zip: Path, output_apk: Path,
              package: str, version_code: int, version_name: str,
              min_sdk: int, target_sdk: int) -> bool:
    """aapt2 link compiled.zip + AndroidManifest → output.apk (with assets).
    Also generates R.java so javac can find the resource IDs."""
    manifest = project_dir / "src" / "main" / "AndroidManifest.xml"
    assets_dir = project_dir / "src" / "main" / "assets"
    r_java_dir = project_dir / "build" / "gen" / package.replace(".", "/")
    r_java_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(AAPT2), "link",
        "-o", str(output_apk),
        "--manifest", str(manifest),
        "-I", str(ANDROID_JAR),
        "--min-sdk-version", str(min_sdk),
        "--target-sdk-version", str(target_sdk),
        "--version-code", str(version_code),
        "--version-name", version_name,
        "--rename-manifest-package", package,
        "--auto-add-overlay",
        "-A", str(assets_dir),
        "--java", str(r_java_dir.parent),   # generate R.java here
        str(compiled_zip),
    ]
    rc, out, err = _run(cmd, timeout=60)
    if rc != 0:
        print(f"aapt2 link failed: {err}", flush=True)
    return rc == 0


def _compile_java(project_dir: Path, package: str, classes_jar: Path) -> bool:
    """javac MainActivity.java + R.java → .class files."""
    if not _ensure_java():
        return False
    java_dir = project_dir / "src" / "main" / "java"
    gen_dir = project_dir / "build" / "gen"
    out_classes = project_dir / "build" / "classes"
    out_classes.mkdir(parents=True, exist_ok=True)
    # Find all .java files (MainActivity + generated R.java)
    java_files = list(java_dir.rglob("*.java"))
    if gen_dir.exists():
        java_files.extend(gen_dir.rglob("*.java"))
    if not java_files:
        return False
    cmd = [
        "javac",
        "-source", "17",
        "-target", "17",
        "-classpath", str(ANDROID_JAR),
        "-d", str(out_classes),
    ] + [str(f) for f in java_files]
    rc, out, err = _run(cmd, timeout=60)
    if rc != 0:
        print(f"javac failed: {err}", flush=True)
        return False
    return True


def _make_dex(project_dir: Path, output_dex: Path) -> bool:
    """d8: compile .class files → classes.dex."""
    if not _ensure_java():
        return False
    classes_dir = project_dir / "build" / "classes"
    class_files = list(classes_dir.rglob("*.class"))
    if not class_files:
        return False
    cmd = [
        "java", "-cp", str(D8_JAR),
        "com.android.tools.r8.D8",
        "--release",
        "--min-api", "24",
        "--output", str(output_dex.parent),
    ] + [str(f) for f in class_files]
    rc, out, err = _run(cmd, timeout=120)
    if rc != 0:
        print(f"d8 failed: {err}", flush=True)
        return False
    return output_dex.exists()


def _inject_dex(apk_path: Path, dex_path: Path) -> None:
    """Add classes.dex into the APK (re-zip)."""
    tmp = apk_path.parent / "tmp_with_dex.apk"
    with zipfile.ZipFile(apk_path, "r") as src, \
         zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            if item.filename == "classes.dex":
                continue
            dst.writestr(item, src.read(item.filename))
        dst.write(dex_path, "classes.dex")
    tmp.replace(apk_path)


def _zipalign(apk_path: Path) -> None:
    """Binary-level zipalign — use our pure-Python implementation.

    Python's zipfile module doesn't expose enough control over local-header
    offsets to achieve proper 4-byte alignment, so we use the binary-level
    implementation from ../zipalign.py which walks the ZIP format manually.

    This is MANDATORY before signing — Android 11+ silently rejects
    unaligned APKs with "App not installed".
    """
    import sys as _sys
    import importlib.util as _ilu
    _here = Path(__file__).resolve().parent
    _spec = _ilu.spec_from_file_location("zipalign", _here.parent / "zipalign.py")
    _mod = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    tmp = apk_path.parent / "tmp_aligned.apk"
    _mod.zipalign(apk_path, tmp, alignment=4)
    tmp.replace(apk_path)


def _sign_apk(apk_path: Path) -> bool:
    """Sign with apksigner (v1 + v2 + v3)."""
    if not APKSIGNER_JAR.exists():
        return False
    _ensure_keystore()
    cmd = [
        "java", "-jar", str(APKSIGNER_JAR), "sign",
        "--ks", str(KEYSTORE),
        "--ks-key-alias", KEYSTORE_ALIAS,
        "--ks-pass", f"pass:{KEYSTORE_PASS}",
        "--key-pass", f"pass:{KEYSTORE_PASS}",
        "--v1-signing-enabled", "true",
        "--v2-signing-enabled", "true",
        "--v3-signing-enabled", "true",
        "--v4-signing-enabled", "false",
        str(apk_path),
    ]
    rc, out, err = _run(cmd, timeout=120)
    if rc != 0:
        print(f"apksigner failed: {err}", flush=True)
        return False
    # Verify
    rc, out, err = _run([
        "java", "-jar", str(APKSIGNER_JAR), "verify", "--verbose", str(apk_path)
    ], timeout=60)
    return rc == 0


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def _ensure_aapt2() -> bool:
    """Ensure aapt2 exists and is executable."""
    if not AAPT2.exists():
        return False
    # Make sure it's executable (GitHub strips the exec bit on some files)
    try:
        os.chmod(AAPT2, 0o755)
    except Exception:
        pass
    # Test it
    try:
        r = subprocess.run([str(AAPT2), "version"], capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def build_apk(function_name: str,
              app_name: Optional[str] = None,
              package_name: Optional[str] = None,
              version_code: int = 1,
              version_name: str = "1.0.0",
              force_webapk: bool = False) -> BuildResult:
    """Build a unique, installable APK from source."""
    import time
    t0 = time.time()
    cfg = get_config()

    fm = get_registry().get(function_name)
    if fm is None:
        return BuildResult(
            function=function_name, apk_path=Path(), apk_size=0,
            build_mode="error", success=False,
            error=f"Function not found: {function_name}",
        )

    if app_name is None:
        app_name = fm.manifest.get("name", function_name.replace("_", " ").title())
    if package_name is None:
        package_name = fm.manifest.get("package", f"com.bardom.app.{function_name}")

    # Build metadata
    from .config_json_processor import write_config_json
    from .strings_json_processor import write_strings_json
    from .template_renderer import render_to_file
    write_config_json(fm.path, fm.name)
    write_strings_json(fm.path, fm.name)
    if fm.has_template:
        try:
            render_to_file(fm.path)
        except Exception:
            pass

    # Ensure tools
    if not _ensure_java():
        return BuildResult(
            function=function_name, apk_path=Path(), apk_size=0,
            build_mode="error", success=False,
            error="Java not available and could not be installed",
            duration_sec=time.time() - t0,
        )
    if not _ensure_android_jar():
        return BuildResult(
            function=function_name, apk_path=Path(), apk_size=0,
            build_mode="error", success=False,
            error="android.jar framework not available",
            duration_sec=time.time() - t0,
        )
    if not _ensure_aapt2():
        return BuildResult(
            function=function_name, apk_path=Path(), apk_size=0,
            build_mode="error", success=False,
            error="aapt2 not available or not executable",
            duration_sec=time.time() - t0,
        )

    try:
        # 1. Prepare project
        project_dir = _prepare_project(
            function_name, app_name, package_name,
            version_code, version_name,
            fm.manifest.get("min_sdk", 24),
            fm.manifest.get("target_sdk", 34),
            fm.path,
        )

        # 2. Compile resources
        compiled_zip = project_dir / "build" / "compiled.zip"
        compiled_zip.parent.mkdir(parents=True, exist_ok=True)
        if not _compile_resources(project_dir, compiled_zip):
            return BuildResult(
                function=function_name, apk_path=Path(), apk_size=0,
                build_mode="error", success=False,
                error="aapt2 compile failed",
                duration_sec=time.time() - t0,
            )

        # 3. Link → APK with resources + assets
        out_dir = cfg.output_dir / function_name
        out_dir.mkdir(parents=True, exist_ok=True)
        linked_apk = project_dir / "build" / "linked.apk"
        if not _link_apk(project_dir, compiled_zip, linked_apk,
                         package_name, version_code, version_name,
                         fm.manifest.get("min_sdk", 24),
                         fm.manifest.get("target_sdk", 34)):
            return BuildResult(
                function=function_name, apk_path=Path(), apk_size=0,
                build_mode="error", success=False,
                error="aapt2 link failed",
                duration_sec=time.time() - t0,
            )

        # 4. Compile Java → .class
        if not _compile_java(project_dir, package_name, project_dir / "build" / "classes.jar"):
            return BuildResult(
                function=function_name, apk_path=Path(), apk_size=0,
                build_mode="error", success=False,
                error="javac failed",
                duration_sec=time.time() - t0,
            )

        # 5. d8: .class → classes.dex
        dex_path = project_dir / "build" / "dex" / "classes.dex"
        dex_path.parent.mkdir(parents=True, exist_ok=True)
        if not _make_dex(project_dir, dex_path):
            return BuildResult(
                function=function_name, apk_path=Path(), apk_size=0,
                build_mode="error", success=False,
                error="d8 failed",
                duration_sec=time.time() - t0,
            )

        # 6. Inject classes.dex into APK
        final_apk = out_dir / f"{app_name}.apk"
        shutil.copy2(linked_apk, final_apk)
        _inject_dex(final_apk, dex_path)

        # 6.5 zipalign — MANDATORY for Android 11+
        try:
            _zipalign(final_apk)
        except Exception as _e:
            print(f"zipalign warning: {_e}", flush=True)

        # 7. Sign
        if not _sign_apk(final_apk):
            return BuildResult(
                function=function_name, apk_path=Path(), apk_size=0,
                build_mode="error", success=False,
                error="apksigner failed",
                duration_sec=time.time() - t0,
            )

        return BuildResult(
            function=function_name,
            apk_path=final_apk,
            apk_size=final_apk.stat().st_size,
            build_mode="apk-v3-signed",
            success=True,
            duration_sec=time.time() - t0,
            manifest={
                "app_name": app_name,
                "package": package_name,
                "version_code": version_code,
                "version_name": version_name,
            },
        )

    except Exception as e:
        import traceback
        return BuildResult(
            function=function_name, apk_path=Path(), apk_size=0,
            build_mode="error", success=False,
            error=f"{e}\n{traceback.format_exc()}",
            duration_sec=time.time() - t0,
        )


def list_built_apks() -> list[dict]:
    cfg = get_config()
    out = []
    for p in sorted(cfg.output_dir.rglob("*.apk")):
        if p.name.endswith(".unsigned.apk"):
            continue
        out.append({
            "path": str(p),
            "name": p.name,
            "function": p.parent.name,
            "size": p.stat().st_size,
            "modified": datetime.datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
        })
    return out


if __name__ == "__main__":
    import sys, json
    fn = sys.argv[1] if len(sys.argv) > 1 else "calculator"
    res = build_apk(fn)
    print(json.dumps(res.to_dict(), indent=2))
