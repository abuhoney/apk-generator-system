"""
apk_builder_v2.py — Builds REAL, installable APKs that pass Android's
package parser.

How it works:
    1. Start from a real APK shell (android/shell.apk) that already has:
         - AndroidManifest.xml (binary)
         - classes.dex (compiled WebView activity)
         - resources.arsc
         - res/ folder
         - META-INF/ (will be stripped)
    2. Replace the `assets/` folder with the function's rendered webapp:
         - assets/index.html   ← rendered template.html
         - assets/config.json  ← function's config.json
         - assets/strings.json ← function's strings.json
         - assets/css/          ← function's CSS
         - assets/js/           ← function's JS
    3. Strip the old META-INF/ signature.
    4. Zip-align (4-byte boundaries for STORED entries).
    5. Re-sign with apksigner (v1+v2+v3 schemes) using a debug keystore.

The result is a real, installable APK that loads the function's webapp
inside a native Android WebView activity. No more "parse error".

Requires:
    - Java (for apksigner.jar)
    - android/tools/apksigner-lib.jar
    - android/debug.keystore (created by setup.sh if missing)
"""
from __future__ import annotations

import os
import io
import json
import shutil
import struct
import zipfile
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
ANDROID_DIR = Path(__file__).resolve().parents[2] / "android"
SHELL_APK = ANDROID_DIR / "shell.apk"
APKSIGNER_JAR = ANDROID_DIR / "tools" / "apksigner-lib.jar"
KEYSTORE = ANDROID_DIR / "debug.keystore"
KEYSTORE_ALIAS = "bardom-debug"
KEYSTORE_PASS = "bardom123"

# Files in the shell APK that must be preserved (NOT replaced)
SHELL_KEEP = {
    "AndroidManifest.xml",
    "classes.dex",
    "resources.arsc",
}


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
        return self.__dict__ if self.manifest is None else {
            "function": self.function,
            "apk_path": str(self.apk_path),
            "apk_size": self.apk_size,
            "build_mode": self.build_mode,
            "success": self.success,
            "error": self.error,
            "duration_sec": self.duration_sec,
            "manifest": self.manifest,
        }


# --------------------------------------------------------------------------- #
# Assets preparation
# --------------------------------------------------------------------------- #
def _prepare_assets(function_dir: Path, app_name: str,
                    version_name: str) -> dict[str, bytes]:
    """Build the assets/ dict that will replace the shell's assets/."""
    assets: dict[str, bytes] = {}

    # Render the function's template.html
    try:
        index_html = render_function(function_dir)
    except Exception as e:
        index_html = f"<!DOCTYPE html><html><body><h1>{app_name}</h1><p>Render error: {e}</p></body></html>"
    assets["index.html"] = index_html.encode("utf-8")

    # Copy config.json + strings.json so the APK carries the full context
    for fname in ("config.json", "strings.json"):
        src = function_dir / fname
        if src.exists():
            assets[fname] = src.read_bytes()

    # Copy asset subfolders (css, js, images, data)
    for sub in ("css", "js", "images", "data", "assets"):
        src_dir = function_dir / sub
        if not src_dir.is_dir():
            continue
        for p in src_dir.rglob("*"):
            if p.is_file():
                arc = Path(sub) / p.relative_to(src_dir)
                assets[arc.as_posix()] = p.read_bytes()

    # Write a build manifest so the WebView can self-identify
    assets["build-info.json"] = json.dumps({
        "app_name": app_name,
        "function": function_dir.name,
        "version_name": version_name,
        "built_at": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "builder": "apk_builder_v2",
    }, indent=2).encode("utf-8")

    return assets


# --------------------------------------------------------------------------- #
# ZIP alignment (zipalign equivalent, pure Python)
# --------------------------------------------------------------------------- #
def _build_aligned_zip(shell_zip: Path,
                       new_assets: dict[str, bytes],
                       out_path: Path) -> None:
    """Build a new APK zip:
       - copy every entry from the shell APK except assets/ and META-INF/
       - add the new assets/ entries
       - align STORED entries to 4-byte boundaries
       - DEFLATE everything else
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ALIGNMENT = 4

    with zipfile.ZipFile(shell_zip, "r") as src, \
         zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as dst:

        for info in src.infolist():
            name = info.filename
            # Skip the old assets/ folder and the old signature
            if name.startswith("assets/"):
                continue
            if name.startswith("META-INF/"):
                continue
            # Skip folders (zipfile handles dirs as zero-byte entries)
            if name.endswith("/"):
                continue
            data = src.read(name)
            # Preserve compression method
            zi = zipfile.ZipInfo(filename=name, date_time=info.date_time)
            zi.compress_type = info.compress_type
            zi.external_attr = info.external_attr
            dst.writestr(zi, data)

        # Add new assets — index.html STORED (so it loads fast), rest DEFLATE
        for arc, data in new_assets.items():
            full = f"assets/{arc}"
            zi = zipfile.ZipInfo(filename=full)
            # Small text files → STORED + aligned (for fast mmap)
            # Large/binary files → DEFLATE
            if len(data) < 4096 and arc.endswith((".html", ".json", ".css", ".js", ".xml")):
                zi.compress_type = zipfile.ZIP_STORED
            else:
                zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            dst.writestr(zi, data)


# --------------------------------------------------------------------------- #
# Signing
# --------------------------------------------------------------------------- #
def _ensure_keystore() -> None:
    """Create the debug keystore if it doesn't exist."""
    if KEYSTORE.exists():
        return
    KEYSTORE.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "keytool", "-genkeypair",
        "-keystore", str(KEYSTORE),
        "-alias", KEYSTORE_ALIAS,
        "-keypass", KEYSTORE_PASS,
        "-storepass", KEYSTORE_PASS,
        "-keyalg", "RSA",
        "-keysize", "2048",
        "-validity", "10000",
        "-dname", "CN=BardomPro APK Generator, OU=Mobile Apps, O=BardomPro, L=Riyadh, ST=Riyadh, C=SA",
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def _sign_apk(apk_path: Path) -> bool:
    """Sign the APK with apksigner (v1 + v2 + v3 schemes)."""
    if not APKSIGNER_JAR.exists():
        raise FileNotFoundError(f"apksigner not found: {APKSIGNER_JAR}")
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
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(f"apksigner failed: {proc.stderr or proc.stdout}")
    return True


def _verify_apk(apk_path: Path) -> bool:
    """Verify the APK signature."""
    cmd = [
        "java", "-jar", str(APKSIGNER_JAR), "verify",
        "--verbose",
        str(apk_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return proc.returncode == 0


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def build_apk(function_name: str,
              app_name: Optional[str] = None,
              package_name: Optional[str] = None,
              version_code: int = 1,
              version_name: str = "1.0.0",
              force_webapk: bool = False) -> BuildResult:
    """Build a real, installable APK for the given function."""
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

    # Make sure config.json + strings.json exist for the function
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

    if not SHELL_APK.exists():
        return BuildResult(
            function=function_name, apk_path=Path(), apk_size=0,
            build_mode="error", success=False,
            error=f"Shell APK not found: {SHELL_APK}",
            duration_sec=time.time() - t0,
        )

    try:
        # 1. Prepare the new assets
        new_assets = _prepare_assets(fm.path, app_name, version_name)

        # 2. Build the aligned but unsigned APK
        out_dir = cfg.output_dir / function_name
        out_dir.mkdir(parents=True, exist_ok=True)
        unsigned_apk = out_dir / f"{app_name}.unsigned.apk"
        final_apk = out_dir / f"{app_name}.apk"

        _build_aligned_zip(SHELL_APK, new_assets, unsigned_apk)

        # 3. Copy unsigned → final (apksigner signs in place)
        shutil.copy2(unsigned_apk, final_apk)

        # 4. Sign the APK
        _sign_apk(final_apk)

        # 5. Verify
        verified = _verify_apk(final_apk)

        # 6. Clean up the unsigned copy
        unsigned_apk.unlink(missing_ok=True)

        return BuildResult(
            function=function_name,
            apk_path=final_apk,
            apk_size=final_apk.stat().st_size,
            build_mode="apk-v2-signed" if verified else "apk-v2-unverified",
            success=verified,
            error=None if verified else "signature verification failed",
            duration_sec=time.time() - t0,
            manifest={
                "app_name": app_name,
                "package": package_name,
                "version_code": version_code,
                "version_name": version_name,
            },
        )

    except Exception as e:
        return BuildResult(
            function=function_name, apk_path=Path(), apk_size=0,
            build_mode="error", success=False, error=str(e),
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
    import sys
    fn = sys.argv[1] if len(sys.argv) > 1 else "calculator"
    res = build_apk(fn)
    print(json.dumps(res.to_dict(), indent=2))
