"""
app.py — Main Flask backend for BardomPro APK Generator.

Endpoints:
    GET  /                         — Dashboard
    GET  /api/health               — Health check
    GET  /api/config               — Safe config (no secrets)
    GET  /api/functions            — List all functions
    GET  /api/functions/<name>     — Function detail
    POST /api/build-config-json    — Build config.json for a function
    POST /api/build-strings-json   — Build strings.json for a function
    POST /api/build-templates      — Build template.html render for a function
    POST /api/build-all-metadata   — Build config+strings+template for all functions
    POST /api/build-apk            — Build an APK for a function
    GET  /api/apks                 — List built APKs
    GET  /download/<filename>     — Download a built APK
    POST /api/github/push          — Push the system to a NEW GitHub repo
    POST /api/github/push-function — Push a single function's folder
    POST /api/render/deploy        — Trigger a Render deploy
    GET  /api/render/health        — Check Render service status
    POST /api/telegram/notify      — Send a message via Telegram bot
    GET  /api/firebase/builds      — List builds recorded in Firebase
    POST /api/firebase/record      — Record a build in Firebase
    GET  /api/package-zip          — Package the entire system as a zip
"""
from __future__ import annotations
import time
import hashlib
import base64

import io
import os
import json
import shutil
import zipfile
import datetime
from pathlib import Path
from typing import Optional

from flask import Flask, request, jsonify, send_file, render_template_string, Response

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine.config import get_config, PROJECT_ROOT
from engine.function_registry import get_registry, reload_registry
from engine.config_json_processor import build_config_json, write_config_json, build_all as build_all_config
from engine.strings_json_processor import build_strings_json, write_strings_json, build_all as build_all_strings
from engine.template_renderer import render_template_file as render_to_file
from engine.apk_builder import build_apk as _v1_build_apk, list_built_apks
# Prefer the v3 builder (real installable APKs built from source with unique package/icon)
try:
    from engine.apk_builder_v3 import build_apk as _v3_build_apk
    _HAVE_V3 = True
except Exception:
    _HAVE_V3 = False
    try:
        from engine.apk_builder_v2 import build_apk as _v2_build_apk
    except Exception:
        _v2_build_apk = _v1_build_apk


def _do_build_apk(function_name, **kwargs):
    """Use v3 (from-source) when available; fall back to v2 (shell) → v1 (webapk)."""
    if _HAVE_V3:
        try:
            return _v3_build_apk(function_name, **kwargs)
        except Exception as e:
            # v3 failed — fall through to v2
            pass
    # Try v2 (shell-based)
    try:
        from engine.apk_builder_v2 import build_apk as _v2_build_apk
        res = _v2_build_apk(function_name, **kwargs)
        if res.success:
            return res
    except Exception:
        pass
    # Fall back to v1 webapk
    return _v1_build_apk(function_name, **kwargs)


# --------------------------------------------------------------------------- #
# Flask app
# --------------------------------------------------------------------------- #
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024   # 200 MB uploads
cfg = get_config()


# --------------------------------------------------------------------------- #
# CORS — allow WebView apps (HTML to APK) to call this API cross-origin
# --------------------------------------------------------------------------- #
@app.after_request
def _add_cors_headers(response):
    origin = request.headers.get("Origin", "*")
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Requested-With"
    response.headers["Access-Control-Max-Age"] = "86400"
    vary = response.headers.get("Vary", "")
    if "Origin" not in vary.split(", "):
        response.headers["Vary"] = (vary + ", Origin") if vary else "Origin"
    return response


@app.before_request
def _handle_preflight():
    if request.method == "OPTIONS":
        return ("", 204)


# --------------------------------------------------------------------------- #
# HTML to APK — custom HTML upload endpoint
# Accepts raw HTML in JSON or multipart, builds an APK from it on-the-fly.
# --------------------------------------------------------------------------- #
@app.route("/api/build-apk-from-html", methods=["POST"])
def build_apk_from_html():
    """Build an APK from arbitrary HTML.

    Accepts JSON: {html, app_name, package_name?, version_name?}
    OR multipart: html_file (file), app_name, package_name?, version_name?
    """
    import traceback
    try:
        import re as _re
        import hashlib as _hashlib
        import time as _time

        html_content = None
        app_name = None
        package_name = None
        version_name = "1.0.0"
        version_code = 1

        if request.files:
            f = request.files.get("html_file") or request.files.get("file")
            if not f:
                return jsonify({"success": False, "error": "html_file required"}), 400
            html_content = f.read().decode("utf-8", errors="replace")
            app_name = request.form.get("app_name", "").strip()
            package_name = request.form.get("package_name") or None
            version_name = request.form.get("version_name", "1.0.0") or "1.0.0"
            try:
                version_code = int(request.form.get("version_code", 1) or 1)
            except Exception:
                version_code = 1
        else:
            data = request.get_json(force=True, silent=True) or {}
            html_content = data.get("html", "")
            if not html_content:
                return jsonify({"success": False, "error": "html required"}), 400
            app_name = (data.get("app_name") or "").strip()
            package_name = data.get("package_name")
            version_name = data.get("version_name", "1.0.0") or "1.0.0"
            try:
                version_code = int(data.get("version_code", 1) or 1)
            except Exception:
                version_code = 1

        if not app_name:
            m = _re.search(r"<title[^>]*>([^<]+)</title>", html_content, _re.I)
            app_name = (m.group(1).strip() if m else "My App")
        # Sanitize
        app_name = _re.sub(r"[^A-Za-z0-9 _-]", "", app_name)[:30] or "MyApp"
        if not package_name:
            slug = _re.sub(r"[^a-z0-9]", "", app_name.lower()) or "myapp"
            package_name = f"com.htmltoapk.{slug}"

        # Create a temp function folder
        functions_dir = PROJECT_ROOT / "functions"
        functions_dir.mkdir(parents=True, exist_ok=True)
        temp_fn_name = "custom_" + _hashlib.md5(
            (app_name + str(_time.time())).encode()).hexdigest()[:8]
        temp_fn_dir = functions_dir / temp_fn_name
        temp_fn_dir.mkdir(parents=True, exist_ok=True)

        # Write the HTML as template.html
        (temp_fn_dir / "template.html").write_text(html_content, encoding="utf-8")
        (temp_fn_dir / "function.json").write_text(json.dumps({
            "name": app_name,
            "version": version_name,
            "package": package_name,
            "entry": "template.html",
            "min_sdk": 24,
            "target_sdk": 34,
            "permissions": ["INTERNET"],
            "description": "Custom APK built from HTML",
        }, indent=2), encoding="utf-8")

        # Handle custom icon if provided (same logic as build_media_apk)
        icon_file = request.files.get("icon_file")
        if icon_file and icon_file.filename:
            try:
                icon_bytes = icon_file.read()
                if icon_bytes[:4] != b'\x89PNG':
                    print(f"[icon] WARNING: not a PNG, may cause aapt2 failure", flush=True)
                (temp_fn_dir / "app_icon.png").write_bytes(icon_bytes)
                print(f"[icon] custom icon saved for HTML build ({len(icon_bytes)} bytes)", flush=True)
            except Exception as e:
                print(f"[icon] failed to save: {e}", flush=True)

        # Force the registry to rescan
        reload_registry()

        # Build the APK
        try:
            from engine.apk_builder_v3 import build_apk as _v3_build_apk
            res = _v3_build_apk(
                temp_fn_name,
                app_name=app_name,
                package_name=package_name,
                version_code=version_code,
                version_name=version_name,
            )
            result = res.to_dict() if hasattr(res, "to_dict") else res
        except Exception as e:
            tb = traceback.format_exc()
            # Fall back to v1 webapk mode
            try:
                res = _v1_build_apk(
                    temp_fn_name,
                    app_name=app_name,
                    package_name=package_name,
                    version_code=version_code,
                    version_name=version_name,
                )
                result = res.to_dict() if hasattr(res, "to_dict") else res
            except Exception as e2:
                return jsonify({
                    "success": False,
                    "error": f"v3 build failed: {e}; v1 fallback also failed: {e2}",
                    "traceback": tb,
                    "function": temp_fn_name,
                }), 500

        # Inject download URL
        if result.get("success") and result.get("apk_path"):
            from pathlib import Path as _P
            apk_filename = _P(result["apk_path"]).name
            result["apk_url"] = f"/download/{temp_fn_name}/{apk_filename}"
            result["apk_name"] = apk_filename
            result["function"] = temp_fn_name

        # NOTE: we do NOT delete temp_fn_dir because the APK is written to
        # _output/<function>/ but Render persists only files in the repo's
        # directory. Keeping the function folder also lets the registry
        # list it for download again later.
        return jsonify(result), (200 if result.get("success") else 500)

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500


@app.route("/")
def dashboard():
    return render_template_string(DASHBOARD_HTML, backend=cfg.backend_url or "local")


@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "version": "5.0.0",
        "timestamp": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "backend_url": cfg.backend_url,
        "functions_count": len(get_registry().all()),
    })


@app.route("/api/config")
def config_route():
    return jsonify(cfg.safe_dict())


@app.route("/api/functions")
def list_functions():
    reg = reload_registry()   # Always rescan so newly added folders show up
    return jsonify(reg.to_dict())


@app.route("/api/functions/<name>")
def function_detail(name: str):
    fm = get_registry().get(name)
    if fm is None:
        return jsonify({"error": f"function not found: {name}"}), 404
    return jsonify(fm.to_dict())


@app.route("/api/build-config-json", methods=["POST"])
def build_config_route():
    data = request.get_json(force=True, silent=True) or {}
    name = data.get("function")
    if not name:
        return jsonify({"error": "function required"}), 400
    fm = get_registry().get(name)
    if fm is None:
        return jsonify({"error": f"function not found: {name}"}), 404
    path = write_config_json(fm.path, fm.name)
    return jsonify({
        "ok": True,
        "function": name,
        "path": str(path),
        "config": build_config_json(fm.path, fm.name),
    })


@app.route("/api/build-strings-json", methods=["POST"])
def build_strings_route():
    data = request.get_json(force=True, silent=True) or {}
    name = data.get("function")
    if not name:
        return jsonify({"error": "function required"}), 400
    fm = get_registry().get(name)
    if fm is None:
        return jsonify({"error": f"function not found: {name}"}), 404
    path = write_strings_json(fm.path, fm.name)
    return jsonify({
        "ok": True,
        "function": name,
        "path": str(path),
        "strings": build_strings_json(fm.path, fm.name),
    })


@app.route("/api/build-templates", methods=["POST"])
def build_templates_route():
    data = request.get_json(force=True, silent=True) or {}
    name = data.get("function")
    if not name:
        return jsonify({"error": "function required"}), 400
    fm = get_registry().get(name)
    if fm is None:
        return jsonify({"error": f"function not found: {name}"}), 404
    if not fm.has_template:
        return jsonify({"error": f"function has no template.html: {name}"}), 400
    path = render_to_file(fm.path)
    return jsonify({
        "ok": True,
        "function": name,
        "path": str(path),
    })


@app.route("/api/build-all-metadata", methods=["POST"])
def build_all_metadata_route():
    """Build config.json + strings.json + rendered.html for every function."""
    data = request.get_json(force=True, silent=True) or {}
    only = data.get("function")
    results = []
    reg = reload_registry()
    for fm in reg.all():
        if only and fm.name != only:
            continue
        cfg_path = write_config_json(fm.path, fm.name)
        str_path = write_strings_json(fm.path, fm.name)
        tpl_path = None
        if fm.has_template:
            try:
                tpl_path = render_to_file(fm.path)
            except Exception as e:
                tpl_path = None
        results.append({
            "function": fm.name,
            "config_json": str(cfg_path),
            "strings_json": str(str_path),
            "rendered_html": str(tpl_path) if tpl_path else None,
        })
    return jsonify({"ok": True, "results": results, "count": len(results)})


@app.route("/api/build-apk", methods=["POST"])
def build_apk_route():
    data = request.get_json(force=True, silent=True) or {}
    name = data.get("function")
    if not name:
        return jsonify({"error": "function required"}), 400
    # Build metadata first so the APK always ships with fresh config.json/strings.json
    fm = get_registry().get(name)
    if fm is None:
        return jsonify({"error": f"function not found: {name}"}), 404
    write_config_json(fm.path, fm.name)
    write_strings_json(fm.path, fm.name)
    if fm.has_template:
        render_to_file(fm.path)

    try:
        res = _do_build_apk(
            name,
            app_name=data.get("app_name"),
            package_name=data.get("package_name"),
            version_code=int(data.get("version_code", 1)),
            version_name=data.get("version_name", "1.0.0"),
            force_webapk=data.get("force_webapk", False),
        )
        return jsonify(res.to_dict())
    except Exception as e:
        import traceback
        return jsonify({
            "function": name,
            "apk_path": "",
            "apk_size": 0,
            "build_mode": "error",
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 200


@app.route("/api/apks")
def list_apks_route():
    return jsonify({"apks": list_built_apks()})


@app.route("/download/<function>/<filename>")
def download_apk(function: str, filename: str):
    # Prevent path traversal
    if "/" in filename or "\\" in filename or "/" in function or "\\" in function:
        return jsonify({"error": "invalid path"}), 400
    p = cfg.output_dir / function / filename
    if not p.exists():
        return jsonify({"error": "file not found"}), 404
    return send_file(p, as_attachment=True, download_name=filename)


# --------------------------------------------------------------------------- #
# Integration routes — loaded lazily so missing deps don't crash startup
# --------------------------------------------------------------------------- #
@app.route("/api/render/health")
def render_health():
    try:
        from integrations.render_client import RenderClient
        rc = RenderClient(cfg.render_api_key, cfg.render_service_id)
        return jsonify(rc.health())
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)})


@app.route("/api/render/deploy", methods=["POST"])
def render_deploy():
    try:
        from integrations.render_client import RenderClient
        rc = RenderClient(cfg.render_api_key, cfg.render_service_id)
        return jsonify(rc.deploy())
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/github/push", methods=["POST"])
def github_push():
    try:
        from integrations.github_client import GitHubClient
        gh = GitHubClient(cfg.github_token, cfg.new_github_repo)
        return jsonify(gh.push_project(PROJECT_ROOT))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/github/push-function", methods=["POST"])
def github_push_function():
    data = request.get_json(force=True, silent=True) or {}
    name = data.get("function")
    if not name:
        return jsonify({"error": "function required"}), 400
    fm = get_registry().get(name)
    if fm is None:
        return jsonify({"error": f"function not found: {name}"}), 404
    try:
        from integrations.github_client import GitHubClient
        gh = GitHubClient(cfg.github_token, cfg.new_github_repo)
        return jsonify(gh.push_folder(fm.path, f"functions/{name}"))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/telegram/notify", methods=["POST"])
def telegram_notify():
    data = request.get_json(force=True, silent=True) or {}
    msg = data.get("message", "Hello from BardomPro APK Generator")
    try:
        from integrations.telegram_bot import TelegramBot
        bot = TelegramBot(cfg.telegram_bot_token, cfg.telegram_admin_chat_id)
        return jsonify(bot.send_message(msg))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/firebase/builds")
def firebase_builds():
    try:
        from integrations.firebase_client import FirebaseClient
        fc = FirebaseClient(cfg.firebase_database_url)
        return jsonify(fc.list_builds())
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/firebase/record", methods=["POST"])
def firebase_record():
    data = request.get_json(force=True, silent=True) or {}
    try:
        from integrations.firebase_client import FirebaseClient
        fc = FirebaseClient(cfg.firebase_database_url)
        return jsonify(fc.record_build(data))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/package-zip", methods=["POST"])
def package_zip():
    """Package the entire project (excluding _builds/_output/.git) as a zip."""
    try:
        from integrations.zip_builder import build_project_zip
        path = build_project_zip(PROJECT_ROOT, cfg.output_dir / "apk-generator-system.zip")
        return jsonify({"ok": True, "path": str(path), "size": path.stat().st_size})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# --------------------------------------------------------------------------- #
# Payload routes — for the main APK's offline-first download
# --------------------------------------------------------------------------- #
@app.route("/api/build-payload", methods=["POST"])
def build_payload():
    """Build payload.json + payload.manifest.json + payload.enc."""
    try:
        from engine.payload_builder import build_all
        result = build_all()
        return jsonify({"ok": True, **result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/payload/manifest")
def payload_manifest():
    """Return the payload manifest (version + sha + size)."""
    from engine.payload_builder import write_payload_manifest
    import json
    path = write_payload_manifest()
    return jsonify(json.loads(path.read_text(encoding="utf-8")))


@app.route("/api/payload/download")
def payload_download():
    """Download the encrypted payload blob."""
    from engine.payload_builder import write_encrypted_payload
    path = write_encrypted_payload()
    return send_file(path, as_attachment=True, download_name="payload.enc")


@app.route("/api/payload/info")
def payload_info():
    """Return payload info (functions count, size, version)."""
    from engine.payload_builder import build_payload_json
    payload = build_payload_json()
    return jsonify({
        "version": payload["version"],
        "functions_count": len(payload["functions"]),
        "function_names": list(payload["functions"].keys()),
        "has_engine_html": bool(payload.get("engine_html")),
    })


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    port = int(os.environ.get("PORT", cfg.port))
    app.run(host="0.0.0.0", port=port, debug=(cfg.node_env != "production"))



# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# App Types Registry — dynamic app type management
# --------------------------------------------------------------------------- #
@app.route("/api/app-types")
def get_app_types():
    """Return the app_types.json registry so the frontend can render buttons dynamically."""
    import json as _json
    types_path = Path(__file__).parent / "app_types.json"
    if not types_path.exists():
        return jsonify({"error": "app_types.json not found"}), 500
    try:
        data = _json.loads(types_path.read_text(encoding="utf-8"))
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# HTML to APK — Media App Builder
# --------------------------------------------------------------------------- #
@app.route("/api/build-media-apk", methods=["POST"])
def build_media_apk():
    """Build a media app APK from a JSON bundle of base64-encoded files."""
    import traceback
    try:
        bundle_file = request.files.get("bundle_file")
        if not bundle_file:
            return jsonify({"success": False, "error": "bundle_file required"}), 400

        app_name = (request.form.get("app_name") or "").strip() or "Media App"
        media_type = (request.form.get("media_type") or "music").strip().lower()
        # Accept any media_type — validated against app_types.json registry
        # (if not in registry, auto-detect template from file contents)
        package_name = request.form.get("package_name") or None
        version_name = request.form.get("version_name") or "1.0.0"
        privacy_url = request.form.get("privacy_url") or ""
        rate_url = request.form.get("rate_url") or ""
        whatsapp_number = request.form.get("whatsapp_number") or ""

        try:
            bundle_data = json.loads(bundle_file.read().decode("utf-8"))
        except Exception as e:
            return jsonify({"success": False, "error": f"Invalid bundle JSON: {e}"}), 400

        files_list = bundle_data.get("files", [])
        if not files_list:
            return jsonify({"success": False, "error": "bundle contains no files"}), 400

        import re
        safe_app_name = re.sub(r"[^A-Za-z0-9 _-]", "", app_name)[:30] or "MediaApp"
        if not package_name:
            slug = re.sub(r"[^a-z0-9]", "", safe_app_name.lower()) or "mediaapp"
            package_name = f"com.htmltoapk.media.{slug}"

        # Dynamic template selection from app_types.json registry
        import json as _json_types
        types_path = Path(__file__).parent / "app_types.json"
        type_config = None
        try:
            types_data = _json_types.loads(types_path.read_text(encoding="utf-8"))
            type_config = types_data.get("types", {}).get(media_type)
        except Exception as e:
            print(f"[media] failed to read app_types.json: {e}", flush=True)

        if type_config and type_config.get("template") and type_config["template"] != "auto":
            # Use the template specified in app_types.json
            template_name = type_config["template"]
            print(f"[media] using template from registry: {template_name} for type '{media_type}'", flush=True)
        elif media_type in ("music", "video", "photo"):
            # Fallback hardcoded mapping for media types
            template_name = {"music": "music_player.html", "video": "video_player.html", "photo": "photo_gallery.html"}[media_type]
        else:
            # Auto-detect content type from files (for 'any', 'zip', and unknown types)
            audio_ext = r"\.(mp3|wav|ogg|m4a|aac|flac|opus|wma)$"
            video_ext = r"\.(mp4|mkv|webm|mov|avi|flv|wmv|m4v|3gp)$"
            image_ext = r"\.(jpe?g|png|gif|webp|bmp|svg|heic)$"
            import re as _re2
            counts = {"audio": 0, "video": 0, "image": 0, "other": 0}
            for f in files_list:
                name = f.get("path", f.get("original_name", "")).lower()
                if _re2.search(audio_ext, name): counts["audio"] += 1
                elif _re2.search(video_ext, name): counts["video"] += 1
                elif _re2.search(image_ext, name): counts["image"] += 1
                else: counts["other"] += 1
            total = sum(counts.values()) or 1
            if counts["audio"] / total > 0.5:
                template_name = "music_player.html"
            elif counts["video"] / total > 0.5:
                template_name = "video_player.html"
            elif counts["image"] / total > 0.5:
                template_name = "photo_gallery.html"
            else:
                template_name = "file_browser.html"
            print(f"[media] auto-detected template: {template_name} (counts: {counts})", flush=True)

        template_path = Path(__file__).parent / "templates" / template_name
        if not template_path.exists():
            return jsonify({"success": False, "error": f"Template not found: {template_name}"}), 500
        template_html = template_path.read_text(encoding="utf-8")

        functions_dir = PROJECT_ROOT / "functions"
        functions_dir.mkdir(parents=True, exist_ok=True)
        temp_fn_name = "media_" + hashlib.md5((safe_app_name + str(time.time())).encode()).hexdigest()[:8]
        temp_fn_dir = functions_dir / temp_fn_name
        temp_fn_dir.mkdir(parents=True, exist_ok=True)

        # Render template with placeholders
        media_bundle = json.dumps({"files": [
            {
                "path": f.get("path", f.get("original_name", f"file_{i}")),
                "title": f.get("title") or Path(f.get("original_name", f"file_{i}")).stem,
                "originalName": f.get("original_name", f"file_{i}"),
                "mime": f.get("mime", "application/octet-stream"),
                "size": f.get("size", 0),
                "duration": f.get("duration", 0),
                "artist": f.get("artist", ""),
            }
            for i, f in enumerate(files_list)
        ]})
        rendered = (template_html
            .replace("__APP_NAME__", safe_app_name)
            .replace("__GENERATED_DATE__", time.strftime("%Y-%m-%d"))
            .replace("__PRIVACY_URL__", privacy_url)
            .replace("__RATE_URL__", rate_url)
            .replace("__WHATSAPP_NUMBER__", whatsapp_number)
            .replace("__MEDIA_BUNDLE__", media_bundle)
        )
        (temp_fn_dir / "template.html").write_text(rendered, encoding="utf-8")

        # Run full build pipeline: data_analyzer + 10 builders
        try:
            from engine.build_pipeline import run_pipeline
            pipeline_results = run_pipeline(temp_fn_dir, media_type)
            print(f"[pipeline] completed with {len(pipeline_results.get('errors',[]))} errors", flush=True)
        except Exception as e:
            print(f"[pipeline] failed: {e}", flush=True)
            import traceback
            print(traceback.format_exc(), flush=True)

        # Write app_config.json into the function dir (gets bundled into assets/webapp/)
        app_config = {
            "app_name": safe_app_name,
            "package_name": package_name,
            "version_name": version_name,
            "media_type": media_type,
            "total_files": len(files_list),
            "total_size_bytes": sum(f.get("size", 0) for f in files_list),
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        (temp_fn_dir / "app_config.json").write_text(json.dumps(app_config, indent=2), encoding="utf-8")
        print(f"[config] app_config.json written ({len(app_config)} keys)", flush=True)

        (temp_fn_dir / "function.json").write_text(json.dumps({
            "name": safe_app_name,
            "version": version_name,
            "package": package_name,
            "entry": "template.html",
            "min_sdk": 24,
            "target_sdk": 34,
            "permissions": ["INTERNET", "READ_EXTERNAL_STORAGE"],
            "description": f"Media app: {media_type} ({len(files_list)} files)",
        }, indent=2), encoding="utf-8")

        # Start capturing stdout for debug
        import io as _io, contextlib as _ctx
        _stdout_capture = _io.StringIO()
        _ctx.redirect_stdout(_stdout_capture).__enter__()
        _ctx.redirect_stderr(_stdout_capture).__enter__()

        # Write media files to a 'media' subfolder — the v3 builder will pick it up
        # via the assets_dir copy in _prepare_project (it copies css/, js/, images/, data/)
        # We patch the v3 builder to also copy 'media/' if present.
        media_dir = temp_fn_dir / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        for i, f in enumerate(files_list):
            try:
                file_data_b64 = f.get("data", "")
                print(f"[media-write] file {i}: path={f.get('path')} data_len={len(file_data_b64)}", flush=True)
                if not file_data_b64:
                    print(f"[media-write]   SKIP: empty data", flush=True)
                    continue
                if file_data_b64.startswith("data:"):
                    file_data_b64 = file_data_b64.split(",", 1)[-1]
                file_bytes = base64.b64decode(file_data_b64)
                file_path = media_dir / f.get("path", f.get("original_name", f"file_{i}"))
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_bytes(file_bytes)
                print(f"[media-write]   WROTE {file_path} ({len(file_bytes)} bytes, exists={file_path.exists()})", flush=True)
                print(f"[media] wrote {file_path} ({len(file_bytes)} bytes)", flush=True)
            except Exception as e:
                print(f"[media] Failed to write file {i}: {e}", flush=True)

        # Verify media files exist
        media_files_check = list(media_dir.rglob("*")) if media_dir.exists() else []
        media_files_count = len([p for p in media_files_check if p.is_file()])
        print(f"[media-check] BEFORE build: media_dir={media_dir} exists={media_dir.exists()} file_count={media_files_count}", flush=True)
        # List all files in function_dir
        all_fn_files = list(temp_fn_dir.rglob("*"))
        print(f"[media-check] function_dir={temp_fn_dir} total_entries={len(all_fn_files)}", flush=True)
        for p in all_fn_files:
            if p.is_file():
                print(f"[media-check]   {p.relative_to(temp_fn_dir)} ({p.stat().st_size})", flush=True)

        # Handle custom icon if provided
        # Client-side Canvas API converts any image to PNG before uploading
        # So we just save the bytes directly
        icon_file = request.files.get("icon_file")
        if icon_file and icon_file.filename:
            try:
                icon_bytes = icon_file.read()
                # Validate it's a PNG (magic bytes)
                if icon_bytes[:4] != b'\x89PNG':
                    print(f"[icon] WARNING: not a PNG (got {icon_bytes[:4].hex()}), may cause aapt2 failure", flush=True)
                (temp_fn_dir / "app_icon.png").write_bytes(icon_bytes)
                print(f"[icon] custom icon saved ({len(icon_bytes)} bytes)", flush=True)
            except Exception as e:
                print(f"[icon] failed to save: {e}", flush=True)

        reload_registry()

        try:
            from engine.apk_builder_v3 import build_apk as _v3_build_apk
            res = _v3_build_apk(
                temp_fn_name,
                app_name=safe_app_name,
                package_name=package_name,
                version_code=1,
                version_name=version_name,
            )
            result = res.to_dict() if hasattr(res, "to_dict") else res
            result["_debug_stdout"] = _stdout_capture.getvalue()
        except Exception as e:
            tb = traceback.format_exc()
            return jsonify({
                "success": False,
                "error": f"v3 build failed: {e}",
                "traceback": tb,
                "function": temp_fn_name,
            }), 500

        if result.get("success") and result.get("apk_path"):
            from pathlib import Path as _P
            apk_filename = _P(result["apk_path"]).name
            result["apk_url"] = f"/download/{temp_fn_name}/{apk_filename}"
            result["apk_name"] = apk_filename
            result["function"] = temp_fn_name

        # Record build stats to Firebase (counts/types only — no media files)
        try:
            _record_build_stats({
                "app_name": safe_app_name,
                "package_name": package_name,
                "media_type": media_type,
                "file_count": len(files_list),
                "total_size_bytes": sum(f.get("size", 0) for f in files_list),
                "version_name": version_name,
                "build_mode": result.get("build_mode", ""),
                "success": result.get("success", False),
                "timestamp": time.time(),
            })
        except Exception as e:
            print(f"[firebase] stats record failed: {e}", flush=True)

        return jsonify(result), (200 if result.get("success") else 500)

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500


# ─────────────────────────────────────────────────────────────────────────────
# /api/build-v2-apk — Full v2 engine pipeline (5-char IDs + RBAC + Offline)
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/api/build-v2-apk", methods=["POST"])
def build_v2_apk():
    """Build an APK using the full v2 engine pipeline.

    Pipeline:
      1. Save uploaded files to functions/<id>/media/
      2. data_analyzer_v2.analyze_data_files() → config.json + strings.json
         (generates 5-char IDs, type detection, dataset structure)
      3. BuilderFactory.run_all() → runs all 10 builders
         (variables, list, control, operator, file, view, math, component, xml_strings, moreblock)
      4. template_renderer.render_template_file() → dynamic template.html
         (embeds config + strings, renders tabs/cards/detail viewer)
      5. native_bridge.generate_all() → native_bridge.js + rbac_engine.js + offline_sync.js
         (Capacitor bridge, 5-role RBAC, IndexedDB sync queue)
      6. Inject native_bridge.js into template.html
      7. apk_builder_v3.build_apk() → aapt2 → javac → d8 → zipalign → apksigner
         (uses pre-generated template.html — does NOT fall back to error HTML)

    Accepts multipart form-data:
      - bundle_file: JSON bundle of base64-encoded files (same format as /api/build-media-apk)
      - app_name: App display name
      - media_type: App type (hospital, supermarket, etc.)
      - package_name: Optional Android package name
      - version_name: Optional version (default 1.0.0)

    Returns the same JSON shape as /api/build-media-apk.
    """
    import traceback as _tb
    import hashlib as _hashlib
    import time as _time
    import base64 as _b64
    try:
        bundle_file = request.files.get("bundle_file")
        if not bundle_file:
            return jsonify({"success": False, "error": "bundle_file required"}), 400

        app_name = (request.form.get("app_name") or "").strip() or "V2 App"
        media_type = (request.form.get("media_type") or "any").strip().lower()
        package_name = request.form.get("package_name") or None
        version_name = request.form.get("version_name") or "1.0.0"

        try:
            bundle_data = json.loads(bundle_file.read().decode("utf-8"))
        except Exception as e:
            return jsonify({"success": False, "error": f"Invalid bundle JSON: {e}"}), 400

        files_list = bundle_data.get("files", [])
        if not files_list:
            return jsonify({"success": False, "error": "bundle contains no files"}), 400

        import re as _re
        safe_app_name = _re.sub(r"[^A-Za-z0-9 _-]", "", app_name)[:30] or "V2App"
        if not package_name:
            slug = _re.sub(r"[^a-z0-9]", "", safe_app_name.lower()) or "v2app"
            package_name = f"com.htmltoapk.v2.{slug}"

        # Create a temp function folder
        functions_dir = PROJECT_ROOT / "functions"
        functions_dir.mkdir(parents=True, exist_ok=True)
        temp_fn_name = "v2_" + _hashlib.md5(
            (app_name + str(_time.time())).encode()).hexdigest()[:8]
        temp_fn_dir = functions_dir / temp_fn_name
        temp_fn_dir.mkdir(parents=True, exist_ok=True)

        # 1. Save uploaded files to media/
        media_dir = temp_fn_dir / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        saved_count = 0
        for f in files_list:
            fname = f.get("path", f.get("original_name", f"file_{saved_count}"))
            fname = _re.sub(r"[^A-Za-z0-9._-]", "_", fname)
            b64 = f.get("content_base64") or f.get("data") or ""
            if not b64:
                # Some bundles send raw text
                raw_text = f.get("content", "")
                if raw_text:
                    (media_dir / fname).write_text(raw_text, encoding="utf-8")
                    saved_count += 1
                continue
            try:
                content_bytes = _b64.b64decode(b64)
                (media_dir / fname).write_bytes(content_bytes)
                saved_count += 1
            except Exception as e:
                print(f"[v2-build] failed to save {fname}: {e}", flush=True)
        print(f"[v2-build] saved {saved_count} files to {media_dir}", flush=True)

        if saved_count == 0:
            return jsonify({"success": False, "error": "No files could be saved"}), 400

        # 2. Run data_analyzer_v2 → config.json + strings.json (5-char IDs)
        try:
            from engine.data_analyzer_v2 import analyze_data_files as _analyze_v2
            config, strings = _analyze_v2(temp_fn_dir, app_name)
            print(f"[v2-build] analyzer: {config['total_ids']} IDs, "
                  f"{config['total_datasets']} datasets, {config['total_items']} items", flush=True)
        except Exception as e:
            return jsonify({"success": False, "error": f"data_analyzer_v2 failed: {e}",
                            "traceback": _tb.format_exc()}), 500

        # 3. Run all 10 builders (Factory + Registry pattern)
        try:
            from engine.builder_factory_v2 import BuilderFactory as _BFactory
            factory = _BFactory()
            factory.register_all()
            results = factory.run_all(config, strings, temp_fn_dir)
            ok = sum(1 for r in results.values() if r and "error" not in r)
            print(f"[v2-build] builders: {ok}/{len(results)} succeeded", flush=True)
        except Exception as e:
            print(f"[v2-build] WARNING: builders failed (continuing): {e}", flush=True)

        # 4. Generate template.html from config + strings (v2 dynamic rendering)
        # First, write app_config.json (WhatsApp channel URL from settingsPickCard)
        app_config_str = request.form.get("app_config", "")
        if app_config_str:
            try:
                app_config = json.loads(app_config_str)
                (temp_fn_dir / "app_config.json").write_text(
                    json.dumps(app_config, indent=2), encoding="utf-8"
                )
                print(f"[v2-build] app_config.json written (whatsapp_channel_url: {app_config.get('whatsapp_channel_url', 'default')})", flush=True)
            except Exception as e:
                print(f"[v2-build] WARNING: app_config parse failed: {e}", flush=True)

        try:
            from engine.template_renderer import render_template_file as _render_v2
            template_html = _render_v2(temp_fn_dir, app_name, media_type)
            print(f"[v2-build] template.html: {len(template_html):,} chars", flush=True)
        except Exception as e:
            return jsonify({"success": False, "error": f"template_renderer failed: {e}",
                            "traceback": _tb.format_exc()}), 500

        # 5. Generate native_bridge.js + rbac_engine.js + offline_sync.js
        native_bridge_size = 0
        rbac_size = 0
        offline_size = 0
        try:
            from engine.native_bridge import generate_native_files as _gen_native
            nb_results = _gen_native(config, strings, temp_fn_dir)
            native_bridge_size = nb_results.get("native_bridge", 0)
            rbac_size = nb_results.get("rbac_engine", 0)
            offline_size = nb_results.get("offline_sync", 0)
            print(f"[v2-build] native_bridge: {native_bridge_size:,} bytes, "
                  f"rbac: {rbac_size:,} bytes, offline: {offline_size:,} bytes", flush=True)
        except Exception as e:
            print(f"[v2-build] WARNING: native_bridge failed (continuing): {e}", flush=True)

        # 6. Inject native_bridge.js + rbac_engine.js into template.html
        try:
            nb_path = temp_fn_dir / "native_bridge.js"
            rbac_path = temp_fn_dir / "rbac_engine.js"
            offline_path = temp_fn_dir / "offline_sync.js"
            injected_scripts = ""
            for script_path in [nb_path, rbac_path, offline_path]:
                if script_path.exists():
                    script_content = script_path.read_text(encoding="utf-8")
                    injected_scripts += f"\n<script>\n{script_content}\n</script>\n"
            if injected_scripts:
                # Inject before </body>
                if "</body>" in template_html.lower():
                    idx = template_html.lower().rfind("</body>")
                    template_html = template_html[:idx] + injected_scripts + template_html[idx:]
                else:
                    template_html += injected_scripts
                # Re-write the updated template.html
                (temp_fn_dir / "template.html").write_text(template_html, encoding="utf-8")
                print(f"[v2-build] injected native bridge scripts into template.html "
                      f"(+{len(injected_scripts):,} chars)", flush=True)
        except Exception as e:
            print(f"[v2-build] WARNING: injection failed (continuing): {e}", flush=True)

        # 7. Write function.json (manifest for apk_builder_v3)
        (temp_fn_dir / "function.json").write_text(json.dumps({
            "name": app_name,
            "version": version_name,
            "package": package_name,
            "entry": "template.html",
            "min_sdk": 24,
            "target_sdk": 34,
            "permissions": ["INTERNET", "ACCESS_NETWORK_STATE",
                            "READ_EXTERNAL_STORAGE", "WRITE_EXTERNAL_STORAGE",
                            "REQUEST_INSTALL_PACKAGES"],
            "description": f"V2 engine APK with {config['total_ids']} IDs, RBAC, Offline Sync",
        }, indent=2), encoding="utf-8")

        # Handle custom icon
        icon_file = request.files.get("icon_file")
        if icon_file and icon_file.filename:
            try:
                icon_bytes = icon_file.read()
                if icon_bytes[:4] != b'\x89PNG':
                    print(f"[v2-build] WARNING: icon not PNG, may fail aapt2", flush=True)
                (temp_fn_dir / "app_icon.png").write_bytes(icon_bytes)
            except Exception as e:
                print(f"[v2-build] icon save failed: {e}", flush=True)

        # Force the registry to rescan
        reload_registry()

        # 8. Build the APK (aapt2 → javac → d8 → zipalign → apksigner)
        #    The fixed _render_function_html will read our pre-generated template.html
        try:
            from engine.apk_builder_v3 import build_apk as _v3_build_apk
            res = _v3_build_apk(
                temp_fn_name,
                app_name=app_name,
                package_name=package_name,
                version_code=1,
                version_name=version_name,
            )
            result = res.to_dict() if hasattr(res, "to_dict") else res
        except Exception as e:
            return jsonify({"success": False, "error": f"apk_builder_v3 failed: {e}",
                            "traceback": _tb.format_exc()}), 500

        # Add v2 metadata to the response
        if isinstance(result, dict) and result.get("success"):
            # Derive apk_name and apk_url (the BuildResult.to_dict() doesn't include these)
            apk_filename = result.get("apk_path", "").split("/")[-1] if result.get("apk_path") else f"{app_name}.apk"
            if not apk_filename.endswith(".apk"):
                apk_filename = f"{app_name.replace(' ', '_')}.apk"
            result["apk_name"] = apk_filename
            result["apk_url"] = f"/download/{temp_fn_name}/{apk_filename}"
            result["package_name"] = package_name
            result["app_name"] = app_name
            result["v2_engine"] = {
                "ids_count": config.get("total_ids", 0),
                "datasets_count": config.get("total_datasets", 0),
                "items_count": config.get("total_items", 0),
                "builders_run": len(results) if 'results' in dir() else 0,
                "native_bridge_bytes": native_bridge_size,
                "rbac_engine_bytes": rbac_size,
                "offline_sync_bytes": offline_size,
                "template_size_bytes": len(template_html),
                "engine_version": "v2.1",
            }
            result["build_mode"] = "apk-v2-engine-signed"

        # Record stats
        try:
            _record_build_stats({
                "function": temp_fn_name,
                "app_name": app_name,
                "media_type": media_type,
                "build_mode": "v2-engine",
                "apk_size": result.get("apk_size", 0) if isinstance(result, dict) else 0,
                "duration_sec": result.get("duration_sec", 0) if isinstance(result, dict) else 0,
                "success": result.get("success", False) if isinstance(result, dict) else False,
                "timestamp": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
            })
        except Exception as e:
            print(f"[firebase] stats record failed: {e}", flush=True)

        return jsonify(result), (200 if result.get("success") else 500)

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": _tb.format_exc(),
        }), 500


# ─────────────────────────────────────────────────────────────────────────────
# /api/build-v3-apk — v3.0 Declarative Web Components + Service Worker
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/api/build-v3-apk", methods=["POST"])
def build_v3_apk():
    """Build an APK using v3.0 declarative Web Components.

    Same pipeline as /api/build-v2-apk but uses template_renderer_v3 instead
    of v2. The v3 renderer produces declarative HTML using custom elements:
      <data-tabs></data-tabs>
      <data-grid dataset="patients"></data-grid>
      <data-field code="hfhcd" label="Name" type="String"></data-field>

    These self-render via Shadow DOM, reducing the imperative HTML/CSS/JS
    from ~270KB (v2) to ~12KB (v3) + 3 small JS files (~30KB total).

    The apk_builder_v3 has been updated to copy core_engine.js, components.js,
    and sw.js to assets/webapp/ so the declarative template can load them.

    Returns the same JSON shape as /api/build-v2-apk plus v3_engine metadata.
    """
    import traceback as _tb
    import hashlib as _hashlib
    import time as _time
    import base64 as _b64
    try:
        bundle_file = request.files.get("bundle_file")
        if not bundle_file:
            return jsonify({"success": False, "error": "bundle_file required"}), 400

        app_name = (request.form.get("app_name") or "").strip() or "V3 App"
        media_type = (request.form.get("media_type") or "any").strip().lower()
        package_name = request.form.get("package_name") or None
        version_name = request.form.get("version_name") or "1.0.0"

        try:
            bundle_data = json.loads(bundle_file.read().decode("utf-8"))
        except Exception as e:
            return jsonify({"success": False, "error": f"Invalid bundle JSON: {e}"}), 400

        files_list = bundle_data.get("files", [])
        if not files_list:
            return jsonify({"success": False, "error": "bundle contains no files"}), 400

        import re as _re
        safe_app_name = _re.sub(r"[^A-Za-z0-9 _-]", "", app_name)[:30] or "V3App"
        if not package_name:
            slug = _re.sub(r"[^a-z0-9]", "", safe_app_name.lower()) or "v3app"
            package_name = f"com.htmltoapk.v3.{slug}"

        # Create a temp function folder
        functions_dir = PROJECT_ROOT / "functions"
        functions_dir.mkdir(parents=True, exist_ok=True)
        temp_fn_name = "v3_" + _hashlib.md5(
            (app_name + str(_time.time())).encode()).hexdigest()[:8]
        temp_fn_dir = functions_dir / temp_fn_name
        temp_fn_dir.mkdir(parents=True, exist_ok=True)

        # 1. Save uploaded files to media/
        media_dir = temp_fn_dir / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        saved_count = 0
        for f in files_list:
            fname = f.get("path", f.get("original_name", f"file_{saved_count}"))
            fname = _re.sub(r"[^A-Za-z0-9._-]", "_", fname)
            b64 = f.get("content_base64") or f.get("data") or ""
            if not b64:
                raw_text = f.get("content", "")
                if raw_text:
                    (media_dir / fname).write_text(raw_text, encoding="utf-8")
                    saved_count += 1
                continue
            try:
                content_bytes = _b64.b64decode(b64)
                (media_dir / fname).write_bytes(content_bytes)
                saved_count += 1
            except Exception as e:
                print(f"[v3-build] failed to save {fname}: {e}", flush=True)
        print(f"[v3-build] saved {saved_count} files to {media_dir}", flush=True)

        if saved_count == 0:
            return jsonify({"success": False, "error": "No files could be saved"}), 400

        # 2. Run data_analyzer_v2 → config.json + strings.json (5-char IDs)
        try:
            from engine.data_analyzer_v2 import analyze_data_files as _analyze_v2
            config, strings = _analyze_v2(temp_fn_dir, app_name)
            print(f"[v3-build] analyzer: {config['total_ids']} IDs, "
                  f"{config['total_datasets']} datasets, {config['total_items']} items", flush=True)
        except Exception as e:
            return jsonify({"success": False, "error": f"data_analyzer_v2 failed: {e}",
                            "traceback": _tb.format_exc()}), 500

        # 3. Run all 10 builders
        builders_ok = 0
        try:
            from engine.builder_factory_v2 import BuilderFactory as _BFactory
            factory = _BFactory()
            factory.register_all()
            results = factory.run_all(config, strings, temp_fn_dir)
            builders_ok = sum(1 for r in results.values() if r and "error" not in r)
            print(f"[v3-build] builders: {builders_ok}/{len(results)} succeeded", flush=True)
        except Exception as e:
            print(f"[v3-build] WARNING: builders failed (continuing): {e}", flush=True)

        # 4. Generate native_bridge.js + rbac_engine.js + offline_sync.js
        native_bridge_size = 0
        rbac_size = 0
        offline_size = 0
        try:
            from engine.native_bridge import generate_native_files as _gen_native
            nb_results = _gen_native(config, strings, temp_fn_dir)
            native_bridge_size = nb_results.get("native_bridge", 0)
            rbac_size = nb_results.get("rbac_engine", 0)
            offline_size = nb_results.get("offline_sync", 0)
            print(f"[v3-build] native_bridge: {native_bridge_size:,} bytes, "
                  f"rbac: {rbac_size:,} bytes, offline: {offline_size:,} bytes", flush=True)
        except Exception as e:
            print(f"[v3-build] WARNING: native_bridge failed (continuing): {e}", flush=True)

        # 5. Generate v3 declarative template (Web Components + Shadow DOM)
        #    This is the v3 magic: replaces ~270KB v2 template with ~12KB declarative HTML
        # First, write app_config.json (WhatsApp channel URL from settingsPickCard)
        app_config_str = request.form.get("app_config", "")
        if app_config_str:
            try:
                app_config = json.loads(app_config_str)
                (temp_fn_dir / "app_config.json").write_text(
                    json.dumps(app_config, indent=2), encoding="utf-8"
                )
                print(f"[v3-build] app_config.json written (whatsapp_channel_url: {app_config.get('whatsapp_channel_url', 'default')})", flush=True)
            except Exception as e:
                print(f"[v3-build] WARNING: app_config parse failed: {e}", flush=True)

        try:
            from engine.template_renderer_v3 import render_template_v3_file as _render_v3
            template_html = _render_v3(temp_fn_dir, app_name, media_type)
            print(f"[v3-build] v3 template.html: {len(template_html):,} chars "
                  f"(declarative Web Components, references core_engine.js + components.js)", flush=True)
        except Exception as e:
            return jsonify({"success": False, "error": f"template_renderer_v3 failed: {e}",
                            "traceback": _tb.format_exc()}), 500

        # 6. Write function.json with 5 Android permissions
        (temp_fn_dir / "function.json").write_text(json.dumps({
            "name": app_name,
            "version": version_name,
            "package": package_name,
            "entry": "template.html",
            "min_sdk": 24,
            "target_sdk": 34,
            "permissions": ["INTERNET", "ACCESS_NETWORK_STATE",
                            "READ_EXTERNAL_STORAGE", "WRITE_EXTERNAL_STORAGE",
                            "REQUEST_INSTALL_PACKAGES"],
            "description": f"V3 engine APK with {config['total_ids']} IDs, Web Components, RBAC, Offline Sync, Service Worker",
        }, indent=2), encoding="utf-8")

        # Handle custom icon
        icon_file = request.files.get("icon_file")
        if icon_file and icon_file.filename:
            try:
                icon_bytes = icon_file.read()
                if icon_bytes[:4] != b'\x89PNG':
                    print(f"[v3-build] WARNING: icon not PNG", flush=True)
                (temp_fn_dir / "app_icon.png").write_bytes(icon_bytes)
            except Exception as e:
                print(f"[v3-build] icon save failed: {e}", flush=True)

        # Force the registry to rescan
        reload_registry()

        # 7. Build the APK (apk_builder_v3 now copies core_engine.js + components.js + sw.js)
        try:
            from engine.apk_builder_v3 import build_apk as _v3_build_apk
            res = _v3_build_apk(
                temp_fn_name,
                app_name=app_name,
                package_name=package_name,
                version_code=1,
                version_name=version_name,
            )
            result = res.to_dict() if hasattr(res, "to_dict") else res
        except Exception as e:
            return jsonify({"success": False, "error": f"apk_builder_v3 failed: {e}",
                            "traceback": _tb.format_exc()}), 500

        # Add v3 metadata to the response
        if isinstance(result, dict) and result.get("success"):
            apk_filename = result.get("apk_path", "").split("/")[-1] if result.get("apk_path") else f"{app_name}.apk"
            if not apk_filename.endswith(".apk"):
                apk_filename = f"{app_name.replace(' ', '_')}.apk"
            result["apk_name"] = apk_filename
            result["apk_url"] = f"/download/{temp_fn_name}/{apk_filename}"
            result["package_name"] = package_name
            result["app_name"] = app_name
            result["v3_engine"] = {
                "ids_count": config.get("total_ids", 0),
                "datasets_count": config.get("total_datasets", 0),
                "items_count": config.get("total_items", 0),
                "builders_run": builders_ok,
                "native_bridge_bytes": native_bridge_size,
                "rbac_engine_bytes": rbac_size,
                "offline_sync_bytes": offline_size,
                "template_size_bytes": len(template_html),
                "core_engine_bytes": (temp_fn_dir / "core_engine.js").stat().st_size if (temp_fn_dir / "core_engine.js").exists() else 0,
                "components_js_bytes": (temp_fn_dir / "components.js").stat().st_size if (temp_fn_dir / "components.js").exists() else 0,
                "sw_js_bytes": (temp_fn_dir / "sw.js").stat().st_size if (temp_fn_dir / "sw.js").exists() else 0,
                "engine_version": "v3.0",
                "renderer": "declarative_web_components",
            }
            result["build_mode"] = "apk-v3-engine-signed"

        # Record stats
        try:
            _record_build_stats({
                "function": temp_fn_name,
                "app_name": app_name,
                "media_type": media_type,
                "build_mode": "v3-engine",
                "apk_size": result.get("apk_size", 0) if isinstance(result, dict) else 0,
                "duration_sec": result.get("duration_sec", 0) if isinstance(result, dict) else 0,
                "success": result.get("success", False) if isinstance(result, dict) else False,
                "timestamp": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
            })
        except Exception as e:
            print(f"[firebase] stats record failed: {e}", flush=True)

        return jsonify(result), (200 if result.get("success") else 500)

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": _tb.format_exc(),
        }), 500


# ─────────────────────────────────────────────────────────────────────────────
# Service Panel endpoints (Firebase-backed, real & direct)
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/service/config")
def service_config_route():
    """Return service configuration: VIP levels, payment methods, coupons, WhatsApp URLs."""
    from engine.firebase_service import get_service_config
    return jsonify(get_service_config())


@app.route("/api/service/user/<device_id>")
def service_user_route(device_id):
    """Fetch user account info + stats. Auto-registers new users."""
    from engine.firebase_service import get_user_info
    return jsonify(get_user_info(device_id))


@app.route("/api/service/user/<device_id>", methods=["POST"])
def service_user_update_route(device_id):
    """Update user profile (name, phone, email)."""
    from engine.firebase_service import update_user_profile
    data = request.get_json(force=True, silent=True) or {}
    result = update_user_profile(
        device_id,
        data.get("userName"),
        data.get("userPhone"),
        data.get("userGmail"),
    )
    return jsonify(result)


@app.route("/api/service/verify-coupon", methods=["POST"])
def service_verify_coupon_route():
    """Verify a coupon code and grant reward.

    JSON body: {device_id, coupon_code, recipientPhone?, recipientEmail?, recipientUserId?}
    """
    from engine.firebase_service import verify_coupon
    data = request.get_json(force=True, silent=True) or {}
    result = verify_coupon(
        data.get("coupon_code", ""),
        data.get("device_id", ""),
        data.get("recipientPhone", ""),
        data.get("recipientEmail", ""),
        data.get("recipientUserId", ""),
    )
    return jsonify(result)


@app.route("/api/service/transfer", methods=["POST"])
def service_transfer_route():
    """Initiate a balance transfer.

    JSON body: {sender_device_id, amount, recipientPhone, recipientEmail, recipientUserId}
    Returns receivingGiftId to share with recipient.
    """
    from engine.firebase_service import transfer_balance
    data = request.get_json(force=True, silent=True) or {}
    result = transfer_balance(
        data.get("sender_device_id", ""),
        int(data.get("amount", 0)),
        data.get("recipientPhone", ""),
        data.get("recipientEmail", ""),
        data.get("recipientUserId", ""),
    )
    return jsonify(result)


@app.route("/api/service/upgrade", methods=["POST"])
def service_upgrade_route():
    """Submit an account upgrade request with proof image.

    JSON body: {device_id, level, payment_method, proof_image_base64?, note?}
    """
    from engine.firebase_service import upgrade_account
    data = request.get_json(force=True, silent=True) or {}
    result = upgrade_account(
        data.get("device_id", ""),
        data.get("level", ""),
        data.get("payment_method", ""),
        data.get("proof_image_base64", ""),
        data.get("note", ""),
    )
    return jsonify(result)


@app.route("/api/service/buy-points", methods=["POST"])
def service_buy_points_route():
    """Submit a buy-points request.

    JSON body: {device_id, amount_usd, payment_method, proof_image_base64?, note?}
    """
    from engine.firebase_service import buy_points
    data = request.get_json(force=True, silent=True) or {}
    result = buy_points(
        data.get("device_id", ""),
        float(data.get("amount_usd", 0)),
        data.get("payment_method", ""),
        data.get("proof_image_base64", ""),
        data.get("note", ""),
    )
    return jsonify(result)


@app.route("/api/service/notifications/<device_id>")
def service_notifications_route(device_id):
    """Fetch all notifications for a user + system notifications."""
    from engine.firebase_service import get_notifications
    return jsonify({"notifications": get_notifications(device_id)})


@app.route("/api/service/notifications/<device_id>/<notification_id>/read", methods=["POST"])
def service_notification_read_route(device_id, notification_id):
    """Mark a notification as read."""
    from engine.firebase_service import mark_notification_read
    return jsonify(mark_notification_read(device_id, notification_id))


@app.route("/api/service/system-stats")
def service_system_stats_route():
    """Fetch system-wide statistics."""
    from engine.firebase_service import get_system_stats
    return jsonify(get_system_stats())


@app.route("/api/service/record-build", methods=["POST"])
def service_record_build_route():
    """Record a build in Firebase and increment user's appsCount."""
    from engine.firebase_service import record_build
    data = request.get_json(force=True, silent=True) or {}
    result = record_build(
        data.get("device_id", ""),
        data.get("app_name", ""),
        int(data.get("apk_size", 0)),
        data.get("function_id", ""),
    )
    return jsonify(result)


# ─────────────────────────────────────────────────────────────────────────────
# Unified Workflow: Analyze → Admin → Save → Build (kept for backward compat)
# ─────────────────────────────────────────────────────────────────────────────
# Replaces 3 separate buttons (v1/v2/v3) with one workflow:
#   1. POST /api/analyze-and-prepare → run engine stages 1-5, return function_id
#   2. GET  /api/admin-html/<function_id> → returns Admin.html for editing
#   3. POST /api/save-edits → persist user edits to config/strings/template
#   4. POST /api/build-prepared-apk → build final APK from saved edits
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/analyze-and-prepare", methods=["POST"])
def analyze_and_prepare_route():
    """Stage 1: Analyze uploaded files and prepare Admin.html for editing.

    Pipeline:
      1. Save uploaded files to functions/<id>/media/
      2. data_analyzer_v2 → config.json + strings.json (5-char IDs)
      3. BuilderFactory.run_all() → 10 builders
      4. native_bridge.generate_native_files() → bridge + rbac + offline
      5. admin_renderer.render_admin_file() → Admin.html (editable)

    Returns function_id which is used in subsequent stages.
    """
    import traceback as _tb
    import hashlib as _hashlib
    import time as _time
    import base64 as _b64
    try:
        bundle_file = request.files.get("bundle_file")
        if not bundle_file:
            return jsonify({"success": False, "error": "bundle_file required"}), 400

        app_name = (request.form.get("app_name") or "").strip() or "App"
        media_type = (request.form.get("media_type") or "any").strip().lower()

        try:
            bundle_data = json.loads(bundle_file.read().decode("utf-8"))
        except Exception as e:
            return jsonify({"success": False, "error": f"Invalid bundle JSON: {e}"}), 400

        files_list = bundle_data.get("files", [])
        if not files_list:
            return jsonify({"success": False, "error": "bundle contains no files"}), 400

        try:
            from engine.admin_workflow import analyze_and_prepare
            result = analyze_and_prepare(
                PROJECT_ROOT / "functions", files_list, app_name, media_type
            )
            if "error" in result:
                return jsonify({"success": False, "error": result["error"]}), 500

            result["success"] = True
            result["admin_url"] = f"/api/admin-html/{result['function_id']}"
            result["save_url"] = f"/api/save-edits"
            result["build_url"] = f"/api/build-prepared-apk"
            return jsonify(result)
        except Exception as e:
            return jsonify({"success": False, "error": str(e),
                            "traceback": _tb.format_exc()}), 500

    except Exception as e:
        return jsonify({"success": False, "error": str(e),
                        "traceback": _tb.format_exc()}), 500


@app.route("/api/admin-html/<function_id>")
def get_admin_html_route(function_id):
    """Stage 2: Return Admin.html for the prepared function."""
    from engine.admin_workflow import get_admin_html
    admin_html = get_admin_html(PROJECT_ROOT / "functions", function_id)
    if admin_html is None:
        return jsonify({"error": f"Admin.html not found for function: {function_id}"}), 404
    return admin_html, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/api/save-edits", methods=["POST"])
def save_edits_route():
    """Stage 3: Persist user edits to config.json/strings.json/template.html.

    Accepts JSON: {
        function_id: str,
        config: dict (edited config.json),
        strings: dict (edited strings.json),
        template_html: str (optional, from GrapesJS)
    }
    """
    import traceback as _tb
    try:
        data = request.get_json(force=True, silent=True) or {}
        function_id = data.get("function_id")
        if not function_id:
            return jsonify({"success": False, "error": "function_id required"}), 400

        config_edits = data.get("config")
        strings_edits = data.get("strings")
        template_edits = data.get("template_html")

        if not config_edits and not strings_edits and not template_edits:
            return jsonify({"success": False, "error": "No edits provided (need config, strings, or template_html)"}), 400

        from engine.admin_workflow import save_edits
        result = save_edits(
            PROJECT_ROOT / "functions", function_id,
            config_edits or {}, strings_edits or {}, template_edits
        )
        if "error" in result:
            return jsonify({"success": False, "error": result["error"]}), 404

        result["success"] = True
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e),
                        "traceback": _tb.format_exc()}), 500


@app.route("/api/build-prepared-apk", methods=["POST"])
def build_prepared_apk_route():
    """Stage 4: Build the final APK from saved edits.

    Accepts JSON or multipart:
        function_id: str (required)
        engine_version: 'v2' or 'v3' (default: v2)
        app_name: str (optional override)
        package_name: str (optional override)
        version_name: str (default 1.0.0)
        icon_file: file (optional, multipart only)
    """
    import traceback as _tb
    import time as _time
    try:
        if request.files:
            # Multipart mode (with optional icon)
            function_id = request.form.get("function_id")
            engine_version = request.form.get("engine_version", "v2")
            app_name = request.form.get("app_name") or None
            package_name = request.form.get("package_name") or None
            version_name = request.form.get("version_name", "1.0.0") or "1.0.0"
            icon_file = request.files.get("icon_file")
            icon_bytes = icon_file.read() if icon_file and icon_file.filename else None
        else:
            data = request.get_json(force=True, silent=True) or {}
            function_id = data.get("function_id")
            engine_version = data.get("engine_version", "v2")
            app_name = data.get("app_name")
            package_name = data.get("package_name")
            version_name = data.get("version_name", "1.0.0") or "1.0.0"
            icon_bytes = None

        if not function_id:
            return jsonify({"success": False, "error": "function_id required"}), 400

        if engine_version not in ("v2", "v3"):
            engine_version = "v2"

        from engine.admin_workflow import build_prepared_apk
        result = build_prepared_apk(
            PROJECT_ROOT / "functions", function_id,
            engine_version=engine_version,
            package_name=package_name,
            app_name=app_name,
            version_name=version_name,
            icon_png_bytes=icon_bytes,
        )

        if isinstance(result, dict) and not result.get("success", True):
            return jsonify(result), 500

        # Record stats
        try:
            _record_build_stats({
                "function": function_id,
                "app_name": result.get("app_name", ""),
                "media_type": "any",
                "build_mode": f"prepared-{engine_version}",
                "apk_size": result.get("apk_size", 0),
                "duration_sec": result.get("duration_sec", 0),
                "success": result.get("success", False),
                "timestamp": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
            })
        except Exception as e:
            print(f"[firebase] stats record failed: {e}", flush=True)

        return jsonify(result), (200 if result.get("success") else 500)

    except Exception as e:
        return jsonify({"success": False, "error": str(e),
                        "traceback": _tb.format_exc()}), 500


@app.route("/api/prepared-functions")
def list_prepared_functions_route():
    """List all prepared (not yet built) functions for the Admin dashboard."""
    from engine.admin_workflow import list_prepared_functions
    prepared = list_prepared_functions(PROJECT_ROOT / "functions")
    return jsonify({"prepared": prepared, "count": len(prepared)})


def _record_build_stats(stats: dict):
    """Record build stats to Firebase RTDB (counts/types only — no media files)."""
    import urllib.request as _ur
    db_url = os.environ.get("FIREBASE_DATABASE_URL")
    if not db_url:
        return
    url = db_url.rstrip("/") + "/builds.json"
    body = json.dumps(stats).encode("utf-8")
    req = _ur.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    _ur.urlopen(req, timeout=10)


@app.route("/api/admin/build-stats")
def admin_build_stats():
    """Return aggregate build statistics from Firebase."""
    import urllib.request as _ur
    db_url = os.environ.get("FIREBASE_DATABASE_URL")
    if not db_url:
        return jsonify({"error": "FIREBASE_DATABASE_URL not configured"}), 500
    try:
        url = db_url.rstrip("/") + "/builds.json?orderBy=\"timestamp\"&limitToLast=50"
        req = _ur.Request(url, headers={"Accept": "application/json"})
        with _ur.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        if not data:
            return jsonify({"total_builds": 0, "by_type": {}, "recent": []})
        builds = list(data.values()) if isinstance(data, dict) else data
        by_type = {}
        for b in builds:
            t = b.get("media_type", "unknown")
            by_type[t] = by_type.get(t, 0) + 1
        recent = sorted(builds, key=lambda x: x.get("timestamp", 0), reverse=True)[:10]
        return jsonify({"total_builds": len(builds), "by_type": by_type, "recent": recent})
    except Exception as e:
        return jsonify({"error": str(e)}), 500




@app.route("/api/debug/function/<fn_name>")
def debug_function_dir(fn_name):
    """Return listing of files in a function dir + build dir for debugging."""
    from pathlib import Path as _P
    from engine.config import get_config as _gc
    fn_dir = PROJECT_ROOT / "functions" / fn_name
    result = {"function": fn_name, "function_dir": str(fn_dir)}
    
    # List function dir
    fn_files = []
    if fn_dir.exists():
        for p in sorted(fn_dir.rglob("*")):
            if p.is_file():
                fn_files.append({"path": str(p.relative_to(fn_dir)), "size": p.stat().st_size})
    result["function_files"] = fn_files
    
    # List build dir (v3)
    build_dir = _gc().build_dir / fn_name / "v3"
    result["build_dir"] = str(build_dir)
    build_files = []
    if build_dir.exists():
        for p in sorted(build_dir.rglob("*")):
            if p.is_file():
                build_files.append({"path": str(p.relative_to(build_dir)), "size": p.stat().st_size})
    result["build_files"] = build_files
    
    return jsonify(result)


