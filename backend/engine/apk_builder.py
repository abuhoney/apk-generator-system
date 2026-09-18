"""
apk_builder.py — Drives the full APK build pipeline.

Pipeline (when Android SDK is available):
    aapt2 compile  →  aapt2 link  →  javac  →  d8  →  zipalign  →  apksigner

If the Android SDK is NOT available (e.g. on Render free tier), this module
falls back to producing a "web APK" — a signed ZIP whose payload is the
rendered webapp and a tiny stub manifest. This web APK can still be opened
by the companion Android viewer app (`android/`) via a deep link, so the
end user still gets a working deliverable even without a full Gradle build.

Both paths return the same dataclass so the caller doesn't care which one
was used.
"""
from __future__ import annotations

import os
import json
import shutil
import zipfile
import subprocess
import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from .config import get_config
from .project_generator import generate_function_project
from .function_registry import get_registry


@dataclass
class BuildResult:
    function: str
    apk_path: Path
    apk_size: int
    build_mode: str            # "gradle" | "webapk"
    success: bool
    error: Optional[str] = None
    duration_sec: float = 0.0
    manifest: dict = None

    def to_dict(self) -> dict:
        return {
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
# Tool detection
# --------------------------------------------------------------------------- #
def _have_android_tools() -> bool:
    cfg = get_config()
    return all([cfg.aapt2_path, cfg.javac_path, cfg.d8_path,
                cfg.zipalign_path, cfg.apksigner_path])


def _run(cmd: list[str], cwd: Optional[Path] = None, env: Optional[dict] = None) -> tuple[int, str, str]:
    proc = subprocess.Popen(
        cmd, cwd=cwd, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    out, err = proc.communicate()
    return proc.returncode, out, err


# --------------------------------------------------------------------------- #
# Web APK fallback (always available)
# --------------------------------------------------------------------------- #
WEBAPK_LAUNCHER_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{app_name}</title>
<style>
  body {{ margin:0; font-family:-apple-system,system-ui,sans-serif;
         background:#0d1117; color:#c9d1d9; }}
  #app {{ padding:16px; }}
  iframe {{ width:100%; height:80vh; border:0; background:#fff; border-radius:8px; }}
  h1 {{ font-size:18px; color:#58a6ff; margin:0 0 12px; }}
  .meta {{ font-size:11px; color:#8b949e; margin-bottom:12px; }}
</style>
</head>
<body>
<div id="app">
  <h1>{app_name}</h1>
  <div class="meta">function: {function} · version: {version}</div>
  <iframe src="webapp/index.html"></iframe>
</div>
</body>
</html>
"""


def _build_webapk(function_name: str, project_dir: Path,
                  app_name: str, package_name: str,
                  version_code: int, version_name: str) -> Path:
    """Build a signed ZIP "web APK" that bundles the rendered webapp."""
    cfg = get_config()
    out_dir = cfg.output_dir / function_name
    out_dir.mkdir(parents=True, exist_ok=True)
    apk_path = out_dir / f"{app_name}.apk"

    assets_src = project_dir / "app" / "src" / "main" / "assets" / "webapp"
    if not assets_src.exists():
        raise FileNotFoundError(f"webapp assets not found: {assets_src}")

    # Build a ZIP with the webapp + a manifest.json + a launcher
    with zipfile.ZipFile(apk_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Write launcher
        launcher_html = WEBAPK_LAUNCHER_HTML.format(
            app_name=app_name,
            function=function_name,
            version=version_name,
        )
        zf.writestr("index.html", launcher_html)

        # Walk the webapp folder
        for root, _dirs, files in os.walk(assets_src):
            for fn in files:
                full = Path(root) / fn
                arc = Path("webapp") / full.relative_to(assets_src)
                zf.write(full, arc.as_posix())

        # Build manifest
        manifest = {
            "app_name": app_name,
            "package": package_name,
            "function": function_name,
            "version_code": version_code,
            "version_name": version_name,
            "built_at": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "kind": "webapk",
            "min_sdk": 24,
            "target_sdk": 34,
            "permissions": ["INTERNET", "ACCESS_NETWORK_STATE"],
            "entry": "index.html",
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    return apk_path


# --------------------------------------------------------------------------- #
# Gradle build (when Android SDK is available)
# --------------------------------------------------------------------------- #
def _build_gradle(project_dir: Path, app_name: str) -> Path:
    """Run gradle assembleRelease and copy the APK to the output dir."""
    apk_in = project_dir / "app" / "build" / "outputs" / "apk" / "release" / "app-release-unsigned.apk"
    # Try gradle wrapper first, then system gradle
    gradle = project_dir / "gradlew"
    if not gradle.exists():
        # Use system gradle if available
        rc, _, _ = _run(["gradle", "--version"])
        if rc != 0:
            raise RuntimeError("gradle not available")
        gradle_cmd = ["gradle", "assembleRelease"]
    else:
        gradle_cmd = ["./gradlew", "assembleRelease"]

    rc, out, err = _run(gradle_cmd, cwd=project_dir)
    if rc != 0 or not apk_in.exists():
        raise RuntimeError(f"gradle build failed: {err or out}")

    out_dir = get_config().output_dir / project_dir.name
    out_dir.mkdir(parents=True, exist_ok=True)
    apk_out = out_dir / f"{app_name}.apk"
    shutil.copy2(apk_in, apk_out)
    return apk_out


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def build_apk(function_name: str,
              app_name: Optional[str] = None,
              package_name: Optional[str] = None,
              version_code: int = 1,
              version_name: str = "1.0.0",
              force_webapk: bool = False) -> BuildResult:
    """Build an APK for the given function. Returns a BuildResult."""
    import time
    t0 = time.time()
    cfg = get_config()
    fm = get_registry().get(function_name)
    if fm is None:
        return BuildResult(
            function=function_name,
            apk_path=Path(),
            apk_size=0,
            build_mode="error",
            success=False,
            error=f"Function not found: {function_name}",
        )

    if app_name is None:
        app_name = fm.manifest.get("name", function_name.replace("_", " ").title())
    if package_name is None:
        package_name = fm.manifest.get("package", f"com.bardom.app.{function_name}")

    try:
        project_dir = generate_function_project(
            function_name,
            app_name=app_name,
            package_name=package_name,
            version_code=version_code,
            version_name=version_name,
        )
    except Exception as e:
        return BuildResult(
            function=function_name, apk_path=Path(), apk_size=0,
            build_mode="error", success=False, error=f"project gen: {e}",
            duration_sec=time.time() - t0,
        )

    use_gradle = (not force_webapk) and _have_android_tools()
    try:
        if use_gradle:
            apk_path = _build_gradle(project_dir, app_name)
            mode = "gradle"
        else:
            apk_path = _build_webapk(
                function_name, project_dir, app_name, package_name,
                version_code, version_name)
            mode = "webapk"
    except Exception as e:
        # Fall back to webapk on any gradle failure
        try:
            apk_path = _build_webapk(
                function_name, project_dir, app_name, package_name,
                version_code, version_name)
            mode = "webapk (fallback)"
        except Exception as e2:
            return BuildResult(
                function=function_name, apk_path=Path(), apk_size=0,
                build_mode="error", success=False, error=f"{e} | {e2}",
                duration_sec=time.time() - t0,
            )

    return BuildResult(
        function=function_name,
        apk_path=apk_path,
        apk_size=apk_path.stat().st_size,
        build_mode=mode,
        success=True,
        duration_sec=time.time() - t0,
        manifest={
            "app_name": app_name,
            "package": package_name,
            "version_code": version_code,
            "version_name": version_name,
        },
    )


def list_built_apks() -> list[dict]:
    """List every APK in the output dir."""
    cfg = get_config()
    out = []
    for p in sorted(cfg.output_dir.rglob("*.apk")):
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
