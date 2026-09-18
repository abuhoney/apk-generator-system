"""
payload_builder.py — Builds the encrypted payload for the main APK.

The payload is a JSON blob containing:
    - version
    - engine_html (the full engine UI)
    - functions (each function's template_html, config_json, strings_json, css, js, manifest)

This payload is:
    1. Built by the backend from the functions/ folder
    2. Encrypted with AES-256-GCM (using a server-side key for distribution)
    3. Pushed to GitHub as payload.enc
    4. The main APK downloads it, decrypts with a device-bound key,
       and injects the engine into its WebView

Note: The payload is encrypted on the DEVICE after download (using the
device-bound key). The server stores the payload as plain JSON (or
lightly obfuscated) on GitHub. The real protection is that the device
re-encrypts it with a key that only that device can derive.
"""
from __future__ import annotations

import json
import os
import base64
import hashlib
import datetime
from pathlib import Path
from typing import Optional

from .config import get_config
from .function_registry import get_registry


def build_payload_json(functions_dir: Optional[Path] = None,
                       engine_html: Optional[str] = None) -> dict:
    """Build the payload as a plain JSON dict.

    Args:
        functions_dir: Directory containing function folders.
                       Defaults to cfg.functions_dir.
        engine_html: The engine UI HTML. If None, a simple UI is generated.
    """
    cfg = get_config()
    functions_dir = functions_dir or cfg.functions_dir

    payload = {
        "version": "6.0.0",
        "built_at": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "functions": {},
        "engine_html": engine_html or _default_engine_html(),
    }

    reg = get_registry()
    for fm in reg.all():
        fn_data = {
            "manifest": fm.manifest,
            "template_html": "",
            "config_json": "",
            "strings_json": "",
            "css": {},
            "js": {},
        }

        # Read template.html
        tpl = fm.path / "template.html"
        if tpl.exists():
            fn_data["template_html"] = tpl.read_text(encoding="utf-8")

        # Read rendered.html if it exists (preferred — already processed)
        rendered = fm.path / "rendered.html"
        if rendered.exists():
            fn_data["template_html"] = rendered.read_text(encoding="utf-8")

        # Read config.json
        cfg_file = fm.path / "config.json"
        if cfg_file.exists():
            fn_data["config_json"] = cfg_file.read_text(encoding="utf-8")

        # Read strings.json
        str_file = fm.path / "strings.json"
        if str_file.exists():
            fn_data["strings_json"] = str_file.read_text(encoding="utf-8")

        # Read CSS files
        css_dir = fm.path / "css"
        if css_dir.is_dir():
            for p in css_dir.rglob("*.css"):
                rel = p.relative_to(css_dir).as_posix()
                fn_data["css"][rel] = p.read_text(encoding="utf-8")

        # Read JS files
        js_dir = fm.path / "js"
        if js_dir.is_dir():
            for p in js_dir.rglob("*.js"):
                rel = p.relative_to(js_dir).as_posix()
                fn_data["js"][rel] = p.read_text(encoding="utf-8")

        payload["functions"][fm.name] = fn_data

    return payload


def _default_engine_html() -> str:
    """Generate a simple engine UI HTML."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
<title>BardomPro — Universal APK Generator</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,system-ui,sans-serif;background:#0d1117;color:#c9d1d9;padding:16px}
header{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:16px;margin-bottom:16px}
header h1{color:#58a6ff;font-size:20px}
header .meta{color:#8b949e;font-size:11px;margin-top:4px}
.stats{display:grid;grid-template-columns:repeat(auto-fill,minmax(100px,1fr));gap:8px;margin-bottom:16px}
.stat{background:#161b22;padding:10px;border-radius:8px;text-align:center}
.stat .v{font-size:18px;font-weight:bold;color:#58a6ff}
.stat .l{font-size:10px;color:#8b949e;margin-top:2px}
.fn-list{display:grid;gap:8px}
.fn{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:14px;cursor:pointer;transition:all .15s}
.fn:hover{border-color:#58a6ff;transform:translateY(-2px)}
.fn .name{color:#e6edf3;font-weight:600;font-size:15px}
.fn .desc{color:#8b949e;font-size:12px;margin-top:4px}
.fn .meta{color:#6e7681;font-size:10px;margin-top:6px}
#fnView{display:none;position:fixed;inset:0;background:#0d1117;z-index:100}
#fnFrame{width:100%;height:100%;border:0}
.back{position:fixed;top:12px;left:12px;z-index:101;background:#21262d;color:#c9d1d9;border:1px solid #30363d;border-radius:6px;padding:8px 14px;cursor:pointer}
.toolbar{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}
.btn{background:#238636;color:#fff;border:none;padding:8px 14px;border-radius:6px;cursor:pointer;font-size:13px}
.btn.alt{background:#21262d;color:#c9d1d9;border:1px solid #30363d}
#buildResult{background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:12px;font-family:monospace;font-size:11px;max-height:200px;overflow:auto;display:none}
</style>
</head>
<body>
<header>
    <h1>BardomPro — Universal APK Generator</h1>
    <div class="meta">Offline-first · v<span id="ver">6.0.0</span> · <span id="fnCount">0</span> functions</div>
</header>

<div class="stats">
    <div class="stat"><div class="v" id="sFns">0</div><div class="l">Functions</div></div>
    <div class="stat"><div class="v" id="sPoints">0</div><div class="l">Points</div></div>
    <div class="stat"><div class="v" id="sDev">—</div><div class="l">Device</div></div>
</div>

<div class="toolbar">
    <button class="btn" onclick="checkUpdates()">Check Updates</button>
    <button class="btn alt" onclick="githubPush()">Push to GitHub</button>
    <button class="btn alt" onclick="telegramNotify()">Telegram Notify</button>
</div>

<div id="buildResult"></div>

<h2 style="color:#58a6ff;font-size:16px;margin-bottom:8px">Available Functions</h2>
<div class="fn-list" id="fnList"></div>

<div id="fnView">
    <button class="back" onclick="closeFn()">← Back</button>
    <iframe id="fnFrame"></iframe>
</div>

<script>
var payload = window.__bardomPayload || {};
var functions = payload.functions || {};

// Populate stats
document.getElementById('ver').textContent = payload.version || '6.0.0';
document.getElementById('fnCount').textContent = Object.keys(functions).length;
document.getElementById('sFns').textContent = Object.keys(functions).length;
if (window.Android) {
    document.getElementById('sPoints').textContent = Android.getPoints();
    document.getElementById('sDev').textContent = Android.getDeviceId().substring(0, 12);
}

// Render function list
var list = document.getElementById('fnList');
var html = '';
Object.keys(functions).forEach(function(id) {
    var fn = functions[id];
    var m = fn.manifest || {};
    html += '<div class="fn" data-id="' + id + '">';
    html += '<div class="name">' + (m.name || id) + '</div>';
    html += '<div class="desc">' + (m.description || '') + '</div>';
    html += '<div class="meta">v' + (m.version || '1.0.0') + ' · ' + id + '</div>';
    html += '<div style="margin-top:8px">';
    html += '<button class="btn" onclick="event.stopPropagation();buildApk(\\'' + id + '\\')">Build APK</button>';
    html += '</div>';
    html += '</div>';
});
list.innerHTML = html;

// Click to open function UI
list.querySelectorAll('.fn').forEach(function(el) {
    el.addEventListener('click', function() {
        var id = el.dataset.id;
        var fn = functions[id];
        if (fn && fn.template_html) {
            var blob = new Blob([fn.template_html], { type: 'text/html' });
            var url = URL.createObjectURL(blob);
            document.getElementById('fnFrame').src = url;
            document.getElementById('fnView').style.display = 'block';
        }
    });
});

function closeFn() {
    document.getElementById('fnView').style.display = 'none';
}

function buildApk(fnId) {
    var result = document.getElementById('buildResult');
    result.style.display = 'block';
    result.textContent = 'Building APK for ' + fnId + '...';
    if (window.Android) {
        var res = Android.buildApk(fnId, '');
        result.textContent = res;
        try {
            var data = JSON.parse(res);
            if (data.ok && data.apk_path) {
                result.textContent += '\\n\\nDownloading APK...';
                Android.downloadApk(data.apk_path, data.function + '.apk');
            }
        } catch (e) {}
    }
}

function checkUpdates() {
    if (window.Android) {
        var res = Android.checkForUpdates();
        alert(res);
    }
}

function githubPush() {
    if (window.Android) {
        var res = Android.githubPush();
        alert(res);
    }
}

function telegramNotify() {
    if (window.Android) {
        var res = Android.telegramSend('7082122839', 'Test from BardomPro APK Generator');
        alert(res);
    }
}
</script>
</body>
</html>
"""


def write_payload_json(out_path: Optional[Path] = None) -> Path:
    """Build the payload and write it as payload.json."""
    cfg = get_config()
    if out_path is None:
        out_path = cfg.project_root / "payload.json"
    payload = build_payload_json()
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def write_payload_manifest(out_path: Optional[Path] = None) -> Path:
    """Write payload.manifest.json (version + sha + size)."""
    cfg = get_config()
    if out_path is None:
        out_path = cfg.project_root / "payload.manifest.json"
    payload_path = cfg.project_root / "payload.json"
    if not payload_path.exists():
        write_payload_json()

    data = payload_path.read_bytes()
    manifest = {
        "version": "6.0.0",
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "url": f"https://raw.githubusercontent.com/{cfg.new_github_repo}/main/payload.enc",
        "updated_at": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    out_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return out_path


def encrypt_payload_for_distribution(payload_json: Optional[str] = None) -> bytes:
    """Lightly obfuscate the payload for GitHub storage.

    NOTE: This is NOT real encryption — the real encryption happens on
    the device with a device-bound key (see PayloadManager.java).
    This step just prevents casual browsing of the payload on GitHub.

    The obfuscation is a simple XOR + base64. The device's loader.js
    reverses this, then PayloadManager.encryptAndStore() re-encrypts
    with the device-bound AES-256-GCM key.
    """
    import random
    if payload_json is None:
        payload = build_payload_json()
        payload_json = json.dumps(payload, ensure_ascii=False)

    # Simple XOR with a random key (key is prepended to the output)
    key = bytes(random.randint(1, 255) for _ in range(32))
    data = payload_json.encode("utf-8")
    xored = bytes(data[i] ^ key[i % len(key)] for i in range(len(data)))
    return key + xored


def write_encrypted_payload(out_path: Optional[Path] = None) -> Path:
    """Build + encrypt the payload and write it as payload.enc."""
    cfg = get_config()
    if out_path is None:
        out_path = cfg.project_root / "payload.enc"
    encrypted = encrypt_payload_for_distribution()
    out_path.write_bytes(encrypted)
    return out_path


def build_all() -> dict:
    """Build payload.json + payload.manifest.json + payload.enc."""
    json_path = write_payload_json()
    manifest_path = write_payload_manifest()
    enc_path = write_encrypted_payload()
    return {
        "payload_json": str(json_path),
        "payload_manifest": str(manifest_path),
        "payload_enc": str(enc_path),
        "size": enc_path.stat().st_size,
    }


if __name__ == "__main__":
    import sys
    result = build_all()
    print(json.dumps(result, indent=2))
