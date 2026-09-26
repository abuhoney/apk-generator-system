#!/usr/bin/env python3
"""Build APK — called by GitHub Actions workflow.
Downloads tools + engine from HuggingFace, runs v2 engine, builds signed APK.
"""
import os, sys, json, base64, time, hashlib, re, shutil
from pathlib import Path

# Read inputs from environment
app_name = os.environ.get("INPUT_APP_NAME", "App")
media_type = os.environ.get("INPUT_MEDIA_TYPE", "any")
package_name = os.environ.get("INPUT_PACKAGE_NAME", "")
engine = os.environ.get("INPUT_ENGINE", "v2")
wa_url = os.environ.get("INPUT_WHATSAPP_URL", "https://whatsapp.com/channel/0029VaijFIC5Ejxq4oG6wX0E")
files_b64 = os.environ.get("INPUT_FILES_B64", "")
ai_prompt = os.environ.get("INPUT_AI_PROMPT", "")
icon_b64 = os.environ.get("INPUT_ICON_B64", "")
hf_token = os.environ.get("HF_TOKEN", "")

print(f"Building: {app_name} ({media_type}, {engine})")

# Setup paths
PROJECT_ROOT = Path(os.getcwd())
BACKEND_DIR = PROJECT_ROOT / "backend"
FUNCTIONS_DIR = BACKEND_DIR / "functions"
OUTPUT_DIR = PROJECT_ROOT / "_output"
FUNCTIONS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Sanitize
safe_name = re.sub(r"[^A-Za-z0-9 _-]", "", app_name)[:30] or "App"
if not package_name:
    slug = re.sub(r"[^a-z0-9]", "", safe_name.lower()) or "app"
    package_name = f"com.htmltoapk.{slug}"

# Create function directory (inside backend/ so engine finds it)
fn_name = "build_" + hashlib.md5((app_name + str(time.time())).encode()).hexdigest()[:8]
fn_dir = FUNCTIONS_DIR / fn_name
fn_dir.mkdir(parents=True, exist_ok=True)
media_dir = fn_dir / "media"
media_dir.mkdir(exist_ok=True)

print(f"Function dir: {fn_dir}")

# Decode files or generate via AI
files_list = []
if ai_prompt:
    print(f"[AI] Generating HTML from prompt...")
    sys.path.insert(0, str(BACKEND_DIR))
    from engine.z_ai_wrapper import ZAIWrapper
    zai = ZAIWrapper()
    html = zai.generate_html_app(ai_prompt, app_name)
    print(f"[AI] HTML: {len(html):,} chars")
    (media_dir / "app.html").write_text(html, encoding="utf-8")
    files_list = [{"path": "app.html"}]
else:
    # Check if files_b64 is a HuggingFace reference (HF:<uploadId>)
    if files_b64.startswith("HF:"):
        upload_id = files_b64[3:]
        print(f"Downloading files from HuggingFace (upload: {upload_id})...")
        from huggingface_hub import hf_hub_download
        import os as _os
        token = _os.environ.get("HF_TOKEN", "") or None
        try:
            local_path = hf_hub_download(
                repo_id="BardomPro/html-to-apk-full-project",
                filename=f"uploads/{upload_id}/bundle.b64",
                repo_type="model",
                token=token,
            )
            files_b64 = Path(local_path).read_text(encoding="utf-8").strip()
            print(f"Downloaded bundle: {len(files_b64):,} chars")
        except Exception as e:
            print(f"Error downloading from HF: {e}")
            # Try alternative path
            try:
                local_path = hf_hub_download(
                    repo_id="BardomPro/html-to-apk-full-project",
                    filename=f"uploads/{upload_id}/bundle.b64",
                    repo_type="model",
                    token=token,
                )
                files_b64 = Path(local_path).read_text(encoding="utf-8").strip()
            except:
                pass

    print(f"Decoding files ({len(files_b64):,} chars)...")
    bundle = json.loads(base64.b64decode(files_b64).decode())
    files_list = bundle.get("files", [])
    for f in files_list:
        fname = re.sub(r"[^A-Za-z0-9._-]", "_", f.get("path", f.get("original_name", "file")))
        b64 = f.get("content_base64") or f.get("data") or ""
        if b64:
            (media_dir / fname).write_bytes(base64.b64decode(b64))
            print(f"  ✓ {fname}")

# Write app_config (WhatsApp — mandatory)
(fn_dir / "app_config.json").write_text(json.dumps({
    "whatsapp_channel_url": wa_url,
    "whatsapp_contact_number": "+967773458975",
}, indent=2), encoding="utf-8")

# Write function.json
(fn_dir / "function.json").write_text(json.dumps({
    "name": app_name, "version": "1.0.0", "package": package_name,
    "entry": "template.html", "min_sdk": 24, "target_sdk": 34,
    "permissions": ["INTERNET", "ACCESS_NETWORK_STATE", "READ_EXTERNAL_STORAGE",
                    "WRITE_EXTERNAL_STORAGE", "REQUEST_INSTALL_PACKAGES"],
}, indent=2), encoding="utf-8")

# Custom icon
if icon_b64:
    try:
        icon_bytes = base64.b64decode(icon_b64)
        if icon_bytes[:4] == b'\x89PNG':
            (fn_dir / "app_icon.png").write_bytes(icon_bytes)
    except:
        pass

# Change to backend/ so engine finds everything with relative paths
os.chdir(BACKEND_DIR)
sys.path.insert(0, str(BACKEND_DIR))

# Run data_analyzer_v2
try:
    from engine.data_analyzer_v2 import analyze_data_files
    config, strings = analyze_data_files(fn_dir, app_name)
    print(f"[engine] {config['total_ids']} IDs, {config['total_datasets']} datasets")
except Exception as e:
    print(f"[engine] analyzer warning: {e}")
    config = {"total_ids": 0, "total_datasets": 0, "total_items": 0}
    strings = {"by_id": {}}

# Run builders
try:
    from engine.builder_factory_v2 import BuilderFactory
    f = BuilderFactory()
    f.register_all()
    f.run_all(config, strings, fn_dir)
    print(f"[engine] builders done")
except Exception as e:
    print(f"[engine] builders warning: {e}")

# Generate native bridge
try:
    from engine.native_bridge import generate_native_files
    generate_native_files(config, strings, fn_dir)
    print(f"[engine] native_bridge done")
except Exception as e:
    print(f"[engine] native_bridge warning: {e}")

# Generate template
from engine.template_renderer import render_template_file
media_tpls = {"music": "music_player.html", "video": "video_player.html", "photo": "photo_gallery.html"}
tpl_name = media_tpls.get(media_type)

if tpl_name and (Path("templates") / tpl_name).exists():
    tpl_html = (Path("templates") / tpl_name).read_text(encoding="utf-8")
    _bundle = json.dumps({"files": [{"path": fl.get("path", ""), "title": "", "size": 0, "duration": 0, "artist": ""} for fl in files_list]})
    template_html = tpl_html.replace("__APP_NAME__", app_name)
    template_html = template_html.replace("__MEDIA_BUNDLE__", _bundle)
    template_html = template_html.replace("__WHATSAPP_NUMBER__", "+967773458975")
    template_html = template_html.replace("__PRIVACY_URL__", "")
    template_html = template_html.replace("__RATE_URL__", "")
    template_html = template_html.replace("__GENERATED_DATE__", time.strftime("%Y-%m-%d"))
    template_html = template_html.replace(
        "const WHATSAPP_CHANNEL_URL='https://whatsapp.com/channel/0029VaijFIC5Ejxq4oG6wX0E';",
        f"const WHATSAPP_CHANNEL_URL='{wa_url}';"
    )
elif ai_prompt:
    template_html = html
    if "WHATSAPP_CHANNEL_URL" not in template_html:
        wa_script = f"<script>const WHATSAPP_CHANNEL_URL='{wa_url}';function openWhatsAppChannel(){{var c=WHATSAPP_CHANNEL_URL.split('/').pop();window.location.href='intent://channel/'+c+'#Intent;package=com.whatsapp;S.browser_fallback_url='+encodeURIComponent(WHATSAPP_CHANNEL_URL)+';end';}}</script>"
        if "</head>" in template_html.lower():
            idx = template_html.lower().rfind("</head>")
            template_html = template_html[:idx] + wa_script + template_html[idx:]
else:
    template_html = render_template_file(fn_dir, app_name, media_type)

# Inject native bridge
injected = ""
for js in ["native_bridge.js", "rbac_engine.js", "offline_sync.js"]:
    p = fn_dir / js
    if p.exists():
        injected += f"\n<script>\n{p.read_text(encoding='utf-8')}\n</script>\n"
if injected and "</body>" in template_html.lower():
    idx = template_html.lower().rfind("</body>")
    template_html = template_html[:idx] + injected + template_html[idx:]
(fn_dir / "template.html").write_text(template_html, encoding="utf-8")

# Build APK
import engine.apk_builder_v3 as ab3
ab3.AAPT2 = Path("build_tools/aapt2")
ab3.ANDROID_JAR = Path("build_tools/android.jar")
ab3.D8_JAR = Path("build_tools/d8.jar")
ab3.APKSIGNER_JAR = Path("build_tools/apksigner-lib.jar")
ab3.KEYSTORE = Path("build_tools/debug.keystore")
ab3.KEYSTORE_ALIAS = "bardom-debug"
ab3.KEYSTORE_PASS = "bardom123"
ab3.ANDROID_DIR = PROJECT_ROOT / "android_source"

from engine.function_registry import reload_registry
reload_registry()

from engine.apk_builder_v3 import build_apk
res = build_apk(fn_name, app_name=app_name, package_name=package_name,
                version_code=1, version_name="1.0.0")
result = res.to_dict() if hasattr(res, "to_dict") else res

if result.get("success"):
    apk_path = Path(result.get("apk_path", ""))
    apk_filename = apk_path.name if apk_path else f"{app_name}.apk"
    out_dir = OUTPUT_DIR / fn_name
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / apk_filename
    if apk_path.exists():
        shutil.copy2(apk_path, out_path)

    print(f"::notice::APK built: {apk_filename} ({out_path.stat().st_size:,} bytes)")

    # Upload to HuggingFace
    if hf_token:
        from huggingface_hub import HfApi
        api = HfApi(token=hf_token)
        hf_path = f"builds/{fn_name}/{apk_filename}"
        api.upload_file(path_or_fileobj=str(out_path), path_in_repo=hf_path,
                       repo_id="BardomPro/html-to-apk-full-project", repo_type="model")
        apk_url = f"https://huggingface.co/BardomPro/html-to-apk-full-project/resolve/main/{hf_path}"
        print(f"::notice::APK uploaded: {apk_url}")

        with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a") as f:
            f.write(f"apk_filename={apk_filename}\n")
            f.write(f"apk_size={out_path.stat().st_size}\n")
            f.write(f"build_id={fn_name}\n")
            f.write(f"apk_url={apk_url}\n")
            f.write(f"success=true\n")

        print(f"✅ BUILD COMPLETE: {apk_filename} ({out_path.stat().st_size:,} bytes)")
        print(f"   Download: {apk_url}")
    else:
        print("⚠ No HF_TOKEN — APK saved as artifact only")
        with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a") as f:
            f.write(f"apk_filename={apk_filename}\n")
            f.write(f"apk_size={out_path.stat().st_size}\n")
            f.write(f"build_id={fn_name}\n")
            f.write(f"success=true\n")
        print(f"✅ BUILD COMPLETE (artifact only): {apk_filename}")
else:
    print(f"::error::Build failed: {result.get('error', 'unknown')}")
    sys.exit(1)
