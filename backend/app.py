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
from engine.template_renderer import render_function, render_to_file
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
        if media_type not in ("music", "video", "photo"):
            return jsonify({"success": False, "error": "media_type must be music, video, or photo"}), 400
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

        template_name = {"music": "music_player.html", "video": "video_player.html", "photo": "photo_gallery.html"}[media_type]
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

        # Write media files to a 'media' subfolder — the v3 builder will pick it up
        # via the assets_dir copy in _prepare_project (it copies css/, js/, images/, data/)
        # We patch the v3 builder to also copy 'media/' if present.
        media_dir = temp_fn_dir / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        for i, f in enumerate(files_list):
            try:
                file_data_b64 = f.get("data", "")
                if not file_data_b64:
                    continue
                if file_data_b64.startswith("data:"):
                    file_data_b64 = file_data_b64.split(",", 1)[-1]
                file_bytes = base64.b64decode(file_data_b64)
                file_path = media_dir / f.get("path", f.get("original_name", f"file_{i}"))
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_bytes(file_bytes)
                print(f"[media] wrote {file_path} ({len(file_bytes)} bytes)", flush=True)
            except Exception as e:
                print(f"[media] Failed to write file {i}: {e}", flush=True)

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
    """Return listing of files in a function dir for debugging."""
    from pathlib import Path as _P
    fn_dir = PROJECT_ROOT / "functions" / fn_name
    if not fn_dir.exists():
        return jsonify({"error": f"function dir not found: {fn_dir}"})
    files = []
    for p in sorted(fn_dir.rglob("*")):
        if p.is_file():
            files.append({"path": str(p.relative_to(fn_dir)), "size": p.stat().st_size})
    return jsonify({"function": fn_name, "dir": str(fn_dir), "files": files})


