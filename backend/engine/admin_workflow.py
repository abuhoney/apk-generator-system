"""
admin_workflow.py — Unified workflow: Analyze → Admin → Save → Build.

Implements the 4-stage workflow:
  1. analyze_and_prepare(): Run engine stages 1-5 (analyzer + builders + native_bridge + admin render)
  2. get_admin_html(): Returns the Admin.html for the prepared function
  3. save_edits(): Persists user edits to config.json/strings.json/template.html
  4. build_prepared_apk(): Builds the final APK from saved edits

This replaces the 3-button approach (v1/v2/v3) with a single unified workflow:
  User uploads files → /api/analyze-and-prepare → Admin.html shown
  User edits in Admin.html → /api/save-edits → edits persisted
  User clicks Build → /api/build-prepared-apk → APK built from saved edits

Author: Principal Software Architect
Version: 2.2.0
"""
from __future__ import annotations

import json
import hashlib
import time
import base64
import re
from pathlib import Path
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════
# Stage 1: Analyze and Prepare
# ═══════════════════════════════════════════════════════════════════════════

def analyze_and_prepare(
    functions_dir: Path,
    files_list: list,
    app_name: str,
    media_type: str = "any",
) -> dict:
    """Stage 1: Save uploaded files + run engine stages 1-5.

    Pipeline:
      1. Save uploaded files to functions/<id>/media/
      2. data_analyzer_v2.analyze_data_files() → config.json + strings.json
      3. BuilderFactory.run_all() → 10 builders
      4. native_bridge.generate_native_files() → native_bridge.js + rbac_engine.js + offline_sync.js
      5. admin_renderer.render_admin_file() → Admin.html (with embedded config/strings for editing)

    Returns:
        Dict with: function_id, ids_count, datasets_count, items_count, builders_run,
                   native_bridge_bytes, rbac_bytes, offline_bytes, admin_html_bytes
    """
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    # 1. Generate function_id and create temp dir
    function_id = "prep_" + hashlib.md5(
        (app_name + str(time.time())).encode()
    ).hexdigest()[:8]
    function_dir = functions_dir / function_id
    function_dir.mkdir(parents=True, exist_ok=True)

    # 2. Save uploaded files to media/
    media_dir = function_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    saved_count = 0
    for f in files_list:
        fname = f.get("path", f.get("original_name", f"file_{saved_count}"))
        fname = re.sub(r"[^A-Za-z0-9._-]", "_", fname)
        b64 = f.get("content_base64") or f.get("data") or ""
        if not b64:
            raw_text = f.get("content", "")
            if raw_text:
                (media_dir / fname).write_text(raw_text, encoding="utf-8")
                saved_count += 1
            continue
        try:
            content_bytes = base64.b64decode(b64)
            (media_dir / fname).write_bytes(content_bytes)
            saved_count += 1
        except Exception as e:
            print(f"[prepare] failed to save {fname}: {e}", flush=True)

    print(f"[prepare] saved {saved_count} files to {media_dir}", flush=True)
    if saved_count == 0:
        return {"error": "No files could be saved"}

    # 3. Run data_analyzer_v2 → config.json + strings.json (5-char IDs)
    try:
        from engine.data_analyzer_v2 import analyze_data_files
        config, strings = analyze_data_files(function_dir, app_name)
        print(f"[prepare] analyzer: {config['total_ids']} IDs, "
              f"{config['total_datasets']} datasets, {config['total_items']} items", flush=True)
    except Exception as e:
        return {"error": f"data_analyzer_v2 failed: {e}"}

    # 4. Run all 10 builders
    builders_ok = 0
    try:
        from engine.builder_factory_v2 import BuilderFactory
        factory = BuilderFactory()
        factory.register_all()
        results = factory.run_all(config, strings, function_dir)
        builders_ok = sum(1 for r in results.values() if r and "error" not in r)
        print(f"[prepare] builders: {builders_ok}/10 succeeded", flush=True)
    except Exception as e:
        print(f"[prepare] WARNING: builders failed (continuing): {e}", flush=True)

    # 5. Generate native_bridge.js + rbac_engine.js + offline_sync.js
    native_bridge_bytes = 0
    rbac_bytes = 0
    offline_bytes = 0
    try:
        from engine.native_bridge import generate_native_files
        nb_results = generate_native_files(config, strings, function_dir)
        native_bridge_bytes = nb_results.get("native_bridge", 0)
        rbac_bytes = nb_results.get("rbac_engine", 0)
        offline_bytes = nb_results.get("offline_sync", 0)
        print(f"[prepare] native_bridge: {native_bridge_bytes:,} bytes, "
              f"rbac: {rbac_bytes:,} bytes, offline: {offline_bytes:,} bytes", flush=True)
    except Exception as e:
        print(f"[prepare] WARNING: native_bridge failed (continuing): {e}", flush=True)

    # 6. Generate Admin.html (the control panel for user editing)
    admin_html_bytes = 0
    try:
        from engine.admin_renderer import render_admin_file
        admin_html = render_admin_file(function_dir, f"{app_name} - Admin")
        admin_html_bytes = len(admin_html)
        print(f"[prepare] Admin.html: {admin_html_bytes:,} bytes", flush=True)
    except Exception as e:
        print(f"[prepare] WARNING: admin_renderer failed (continuing): {e}", flush=True)

    # 7. Write function.json (manifest for apk_builder_v3)
    package_name = f"com.htmltoapk.prep.{re.sub(r'[^a-z0-9]', '', app_name.lower()) or 'app'}"
    (function_dir / "function.json").write_text(json.dumps({
        "name": app_name,
        "version": "1.0.0",
        "package": package_name,
        "entry": "template.html",
        "min_sdk": 24,
        "target_sdk": 34,
        "permissions": ["INTERNET", "ACCESS_NETWORK_STATE",
                       "READ_EXTERNAL_STORAGE", "WRITE_EXTERNAL_STORAGE",
                       "REQUEST_INSTALL_PACKAGES"],
        "description": f"Prepared for build with {config['total_ids']} IDs",
        "prepared_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "prepared": True,
    }, indent=2), encoding="utf-8")

    return {
        "function_id": function_id,
        "ids_count": config["total_ids"],
        "datasets_count": config["total_datasets"],
        "items_count": config["total_items"],
        "builders_run": builders_ok,
        "native_bridge_bytes": native_bridge_bytes,
        "rbac_bytes": rbac_bytes,
        "offline_bytes": offline_bytes,
        "admin_html_bytes": admin_html_bytes,
        "app_name": app_name,
        "package_name": package_name,
        "media_type": media_type,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Stage 2: Get Admin HTML
# ═══════════════════════════════════════════════════════════════════════════

def get_admin_html(functions_dir: Path, function_id: str) -> Optional[str]:
    """Stage 2: Return the Admin.html for the prepared function."""
    function_dir = functions_dir / function_id
    admin_path = function_dir / "Admin.html"
    if not admin_path.exists():
        return None
    return admin_path.read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════
# Stage 3: Save Edits
# ═══════════════════════════════════════════════════════════════════════════

def save_edits(
    functions_dir: Path,
    function_id: str,
    config_edits: dict,
    strings_edits: dict,
    template_edits: Optional[str] = None,
) -> dict:
    """Stage 3: Persist user edits to config.json/strings.json/template.html.

    Args:
        function_id: The prepared function ID (prep_xxxxxxxx)
        config_edits: Edited config.json dict
        strings_edits: Edited strings.json dict
        template_edits: Optional edited template.html string (from GrapesJS)

    Returns:
        Dict with status and file sizes
    """
    function_dir = functions_dir / function_id
    if not function_dir.exists():
        return {"error": f"Function not found: {function_id}"}

    saved_files = []

    # Save config.json
    if config_edits:
        config_path = function_dir / "config.json"
        config_path.write_text(
            json.dumps(config_edits, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        saved_files.append({"file": "config.json", "size": config_path.stat().st_size})
        print(f"[save] config.json: {config_path.stat().st_size:,} bytes", flush=True)

    # Save strings.json
    if strings_edits:
        strings_path = function_dir / "strings.json"
        strings_path.write_text(
            json.dumps(strings_edits, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        saved_files.append({"file": "strings.json", "size": strings_path.stat().st_size})
        print(f"[save] strings.json: {strings_path.stat().st_size:,} bytes", flush=True)

    # Save template.html (if user edited via GrapesJS or Blockly)
    if template_edits:
        template_path = function_dir / "template.html"
        template_path.write_text(template_edits, encoding="utf-8")
        saved_files.append({"file": "template.html", "size": template_path.stat().st_size})
        print(f"[save] template.html: {template_path.stat().st_size:,} bytes", flush=True)

    return {
        "function_id": function_id,
        "saved_files": saved_files,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Stage 4: Build Prepared APK
# ═══════════════════════════════════════════════════════════════════════════

def build_prepared_apk(
    functions_dir: Path,
    function_id: str,
    engine_version: str = "v2",
    package_name: Optional[str] = None,
    app_name: Optional[str] = None,
    version_name: str = "1.0.0",
    icon_png_bytes: Optional[bytes] = None,
) -> dict:
    """Stage 4: Build the final APK from saved edits.

    Args:
        function_id: The prepared function ID
        engine_version: 'v2' (imperative) or 'v3' (declarative Web Components)
        package_name: Optional override
        app_name: Optional override
        version_name: APK version
        icon_png_bytes: Optional custom icon

    Returns:
        Build result dict from apk_builder_v3
    """
    function_dir = functions_dir / function_id
    if not function_dir.exists():
        return {"error": f"Function not found: {function_id}"}

    # Load function.json for defaults
    function_json_path = function_dir / "function.json"
    if function_json_path.exists():
        fj = json.loads(function_json_path.read_text(encoding="utf-8"))
    else:
        fj = {}

    if app_name is None:
        app_name = fj.get("name", function_id)
    if package_name is None:
        package_name = fj.get("package", f"com.htmltoapk.prep.{function_id}")

    # Update function.json with final values
    fj.update({
        "name": app_name,
        "package": package_name,
        "version": version_name,
        "prepared": False,  # No longer just prepared — being built now
        "built": True,
    })
    function_json_path.write_text(json.dumps(fj, indent=2), encoding="utf-8")

    # Save custom icon if provided
    if icon_png_bytes:
        if icon_png_bytes[:4] == b'\x89PNG':
            (function_dir / "app_icon.png").write_bytes(icon_png_bytes)
        else:
            print(f"[build] WARNING: icon not PNG, skipping", flush=True)

    # Re-generate template.html from saved config + strings if engine version requested
    # (only if user didn't already save template.html via GrapesJS)
    if engine_version == "v3":
        try:
            from engine.template_renderer_v3 import render_template_v3_file
            render_template_v3_file(function_dir, app_name, fj.get("media_type", "any"))
            print(f"[build] v3 template.html generated", flush=True)
        except Exception as e:
            print(f"[build] WARNING: v3 template_renderer failed: {e}", flush=True)
    else:
        # v2: re-generate template.html from saved config/strings
        if not (function_dir / "template.html").exists() or \
           (function_dir / "template.html").stat().st_size < 1000:
            try:
                from engine.template_renderer import render_template_file
                render_template_file(function_dir, app_name, fj.get("media_type", "any"))
                print(f"[build] v2 template.html generated", flush=True)
            except Exception as e:
                print(f"[build] WARNING: v2 template_renderer failed: {e}", flush=True)

    # Inject native_bridge.js + rbac_engine.js + offline_sync.js into template.html
    try:
        template_path = function_dir / "template.html"
        if template_path.exists():
            template_html = template_path.read_text(encoding="utf-8")
            injected = ""
            for js_name in ["native_bridge.js", "rbac_engine.js", "offline_sync.js"]:
                js_path = function_dir / js_name
                if js_path.exists():
                    script_content = js_path.read_text(encoding="utf-8")
                    injected += f"\n<script>\n{script_content}\n</script>\n"
            if injected and "</body>" in template_html.lower():
                idx = template_html.lower().rfind("</body>")
                template_html = template_html[:idx] + injected + template_html[idx:]
                template_path.write_text(template_html, encoding="utf-8")
                print(f"[build] injected {len(injected):,} chars of native bridge scripts", flush=True)
    except Exception as e:
        print(f"[build] WARNING: injection failed: {e}", flush=True)

    # Force registry reload and build APK via apk_builder_v3
    # (apk_builder_v3 has been updated to preserve v2 config/strings and copy v3 JS files)
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    try:
        # Reload function registry
        from engine.function_registry import reload_registry
        reload_registry()

        # Build the APK
        from engine.apk_builder_v3 import build_apk
        res = build_apk(
            function_id,
            app_name=app_name,
            package_name=package_name,
            version_code=1,
            version_name=version_name,
        )
        result = res.to_dict() if hasattr(res, "to_dict") else res

        # Add apk_url and apk_name (BuildResult.to_dict() doesn't include these)
        if isinstance(result, dict) and result.get("success"):
            apk_filename = result.get("apk_path", "").split("/")[-1] if result.get("apk_path") else f"{app_name}.apk"
            if not apk_filename.endswith(".apk"):
                apk_filename = f"{app_name.replace(' ', '_')}.apk"
            result["apk_name"] = apk_filename
            result["apk_url"] = f"/download/{function_id}/{apk_filename}"
            result["package_name"] = package_name
            result["app_name"] = app_name
            result["engine_version"] = engine_version
            result["build_mode"] = f"apk-{engine_version}-engine-signed"

            # Add edit summary
            result["edit_summary"] = {
                "config_json_size": (function_dir / "config.json").stat().st_size if (function_dir / "config.json").exists() else 0,
                "strings_json_size": (function_dir / "strings.json").stat().st_size if (function_dir / "strings.json").exists() else 0,
                "template_html_size": (function_dir / "template.html").stat().st_size if (function_dir / "template.html").exists() else 0,
                "admin_html_size": (function_dir / "Admin.html").stat().st_size if (function_dir / "Admin.html").exists() else 0,
                "function_id": function_id,
            }

        return result
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
            "function_id": function_id,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Helper: List Prepared Functions
# ═══════════════════════════════════════════════════════════════════════════

def list_prepared_functions(functions_dir: Path) -> list:
    """List all prepared (not yet built) functions."""
    prepared = []
    if not functions_dir.exists():
        return prepared
    for fn_dir in functions_dir.iterdir():
        if not fn_dir.is_dir() or not fn_dir.name.startswith("prep_"):
            continue
        fj_path = fn_dir / "function.json"
        if not fj_path.exists():
            continue
        try:
            fj = json.loads(fj_path.read_text(encoding="utf-8"))
            if fj.get("prepared") and not fj.get("built"):
                cfg_path = fn_dir / "config.json"
                cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
                prepared.append({
                    "function_id": fn_dir.name,
                    "app_name": fj.get("name", "?"),
                    "media_type": fj.get("media_type", "any"),
                    "ids_count": cfg.get("total_ids", 0),
                    "datasets_count": cfg.get("total_datasets", 0),
                    "items_count": cfg.get("total_items", 0),
                    "prepared_at": fj.get("prepared_at", "?"),
                    "has_admin": (fn_dir / "Admin.html").exists(),
                })
        except Exception:
            pass
    return prepared
