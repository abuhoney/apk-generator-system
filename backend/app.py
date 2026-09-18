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
# Prefer the v2 builder (real installable APKs) when the shell + apksigner are present
try:
    from engine.apk_builder_v2 import build_apk as _v2_build_apk
    _HAVE_V2 = True
except Exception:
    _HAVE_V2 = False


def _do_build_apk(function_name, **kwargs):
    """Use v2 builder (real APK) when available; fall back to v1 webapk."""
    if _HAVE_V2:
        try:
            return _v2_build_apk(function_name, **kwargs)
        except Exception as e:
            # v2 failed (missing Java/apksigner/shell) — fall back to v1
            res = _v1_build_apk(function_name, **kwargs)
            if not res.success:
                res.error = f"v2 failed ({e}); v1 also failed: {res.error}"
            else:
                res.build_mode = f"webapk (v2 unavailable: {e})"
            return res
    return _v1_build_apk(function_name, **kwargs)


# --------------------------------------------------------------------------- #
# Flask app
# --------------------------------------------------------------------------- #
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024   # 200 MB uploads
cfg = get_config()


# --------------------------------------------------------------------------- #
# Dashboard HTML (served inline — full dashboard in dashboard/index.html)
# --------------------------------------------------------------------------- #
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BardomPro APK Generator</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
     background:#0d1117;color:#c9d1d9;padding:20px;line-height:1.5}
.container{max-width:1200px;margin:0 auto}
h1{color:#58a6ff;font-size:22px;margin-bottom:4px}
.sub{color:#8b949e;font-size:13px;margin-bottom:20px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:800px){.grid{grid-template-columns:1fr}}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;margin-bottom:16px}
.card h3{color:#58a6ff;font-size:14px;margin-bottom:12px}
.btn{background:#238636;color:#fff;border:none;padding:8px 16px;border-radius:6px;
     cursor:pointer;font-size:13px;margin:4px 0}
.btn:hover{background:#2ea043}
.btn.alt{background:#21262d;color:#c9d1d9;border:1px solid #30363d}
.btn.alt:hover{background:#30363d}
pre{background:#0d1117;padding:10px;border-radius:6px;overflow:auto;
    color:#8b949e;font-size:12px;max-height:240px}
input,select,textarea{width:100%;background:#0d1117;color:#c9d1d9;
     border:1px solid #30363d;border-radius:6px;padding:8px;font-size:13px;
     font-family:inherit;margin-bottom:8px}
label{display:block;margin:8px 0 4px;font-size:12px;color:#8b949e}
.stat{display:inline-block;background:#21262d;padding:4px 12px;border-radius:12px;
      font-size:11px;color:#8b949e;margin-right:8px}
.stat b{color:#58a6ff}
</style>
</head>
<body>
<div class="container">
<h1>BardomPro APK Generator</h1>
<div class="sub">Universal function-based APK generation system · v5.0.0</div>

<div class="card">
  <h3>System Status</h3>
  <div>
    <span class="stat">Functions: <b id="fnCount">—</b></span>
    <span class="stat">Built APKs: <b id="apkCount">—</b></span>
    <span class="stat">Backend: <b id="backend">{{backend}}</b></span>
    <span class="stat">Render: <b id="renderStatus">checking…</b></span>
  </div>
</div>

<div class="card">
  <h3>Available Functions</h3>
  <div id="functions">Loading…</div>
</div>

<div class="card">
  <h3>Build Pipeline</h3>
  <label>Function name</label>
  <input id="fnName" placeholder="calculator">
  <label>App name (optional)</label>
  <input id="appName" placeholder="Calculator">
  <label>Package name (optional)</label>
  <input id="pkgName" placeholder="com.bardom.app.calculator">
  <label>Version</label>
  <input id="version" value="1.0.0">
  <div style="margin-top:8px">
    <button class="btn" onclick="buildApk()">Build APK</button>
    <button class="btn alt" onclick="buildMetadata()">Build config+strings+template</button>
    <button class="btn alt" onclick="buildAllMetadata()">Build ALL metadata</button>
  </div>
  <pre id="buildResult">Click a button to start.</pre>
</div>

<div class="card">
  <h3>Built APKs</h3>
  <div id="apks">Loading…</div>
</div>

<div class="card">
  <h3>Deploy</h3>
  <button class="btn" onclick="githubPush()">Push to GitHub (new repo)</button>
  <button class="btn alt" onclick="renderDeploy()">Deploy to Render</button>
  <button class="btn alt" onclick="packageZip()">Package as ZIP</button>
  <button class="btn alt" onclick="telegramNotify()">Send Telegram message</button>
  <pre id="deployResult"></pre>
</div>

</div>
<script>
async function api(path, opts={}) {
  const r = await fetch(path, {headers:{'Content-Type':'application/json'}, ...opts});
  return r.json();
}
async function refresh() {
  const fns = await api('/api/functions');
  document.getElementById('fnCount').textContent = fns.functions.length;
  document.getElementById('functions').innerHTML = fns.functions.map(f =>
    `<div style="padding:6px 0;border-bottom:1px solid #30363d">
       <b style="color:#58a6ff">${f.name}</b>
       <span style="color:#8b949e;font-size:11px;margin-left:8px">${f.languages.join(', ')}</span>
       <span style="color:#8b949e;font-size:11px;margin-left:8px">${f.has_template?'HTML':''} ${f.has_handler?'PY':''} ${f.has_config_json?'CFG':''} ${f.has_strings_json?'STR':''}</span>
     </div>`).join('');
  const apks = await api('/api/apks');
  document.getElementById('apkCount').textContent = apks.apks.length;
  document.getElementById('apks').innerHTML = apks.apks.length ?
    apks.apks.map(a => `<div style="padding:6px 0;border-bottom:1px solid #30363d">
       <a href="/download/${a.function}/${a.name}" style="color:#58a6ff">${a.name}</a>
       <span style="color:#8b949e;font-size:11px;margin-left:8px">${(a.size/1024).toFixed(1)} KB</span>
     </div>`).join('') : '<i style="color:#8b949e">No APKs yet</i>';
}
async function buildApk() {
  const body = JSON.stringify({
    function: document.getElementById('fnName').value,
    app_name: document.getElementById('appName').value || undefined,
    package_name: document.getElementById('pkgName').value || undefined,
    version_name: document.getElementById('version').value,
  });
  document.getElementById('buildResult').textContent = 'Building…';
  const r = await api('/api/build-apk', {method:'POST', body});
  document.getElementById('buildResult').textContent = JSON.stringify(r, null, 2);
  refresh();
}
async function buildMetadata() {
  const body = JSON.stringify({function: document.getElementById('fnName').value});
  document.getElementById('buildResult').textContent = 'Building metadata…';
  const r = await api('/api/build-all-metadata', {method:'POST', body});
  document.getElementById('buildResult').textContent = JSON.stringify(r, null, 2);
  refresh();
}
async function buildAllMetadata() {
  document.getElementById('buildResult').textContent = 'Building ALL metadata…';
  const r = await api('/api/build-all-metadata', {method:'POST', body:'{}'});
  document.getElementById('buildResult').textContent = JSON.stringify(r, null, 2);
  refresh();
}
async function githubPush() {
  document.getElementById('deployResult').textContent = 'Pushing to GitHub…';
  const r = await api('/api/github/push', {method:'POST', body:'{}'});
  document.getElementById('deployResult').textContent = JSON.stringify(r, null, 2);
}
async function renderDeploy() {
  document.getElementById('deployResult').textContent = 'Deploying to Render…';
  const r = await api('/api/render/deploy', {method:'POST', body:'{}'});
  document.getElementById('deployResult').textContent = JSON.stringify(r, null, 2);
}
async function packageZip() {
  document.getElementById('deployResult').textContent = 'Packaging ZIP…';
  const r = await api('/api/package-zip', {method:'POST', body:'{}'});
  document.getElementById('deployResult').textContent = JSON.stringify(r, null, 2);
}
async function telegramNotify() {
  document.getElementById('deployResult').textContent = 'Sending…';
  const r = await api('/api/telegram/notify', {method:'POST',
    body: JSON.stringify({message:'Test from BardomPro APK Generator'})});
  document.getElementById('deployResult').textContent = JSON.stringify(r, null, 2);
}
refresh();
fetch('/api/render/health').then(r=>r.json()).then(d=>{
  document.getElementById('renderStatus').textContent = d.status || 'unknown';
}).catch(()=>{document.getElementById('renderStatus').textContent='offline'});
</script>
</body>
</html>
"""


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
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

    res = _do_build_apk(
        name,
        app_name=data.get("app_name"),
        package_name=data.get("package_name"),
        version_code=int(data.get("version_code", 1)),
        version_name=data.get("version_name", "1.0.0"),
        force_webapk=data.get("force_webapk", False),
    )
    return jsonify(res.to_dict())


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
# Entry point
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    port = int(os.environ.get("PORT", cfg.port))
    app.run(host="0.0.0.0", port=port, debug=(cfg.node_env != "production"))
