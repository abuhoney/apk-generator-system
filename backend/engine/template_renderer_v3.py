"""
template_renderer_v3.py — v3.0 Declarative Template Renderer

Generates template.html using Web Components (declarative HTML)
instead of imperative HTML (v2.1 = 194KB → v3.0 = ~12KB).

Output uses:
  <data-tabs></data-tabs>
  <data-grid dataset="patients"></data-grid>
  <data-field code="hfhcd" label="Name" type="String"></data-field>

Instead of generating 194KB of tables/cards/divs, it generates
~12KB of declarative custom elements that self-render via Shadow DOM.

Author: Principal Software Architect
Version: 3.0.0
"""
from __future__ import annotations

import json
from pathlib import Path


def render_template_v3(config: dict, strings: dict, app_name: str = "Universal App",
                       media_type: str = "any", app_config: dict = None) -> str:
    """Generate a lightweight template.html using Web Components.
    
    Args:
        config: config.json dict
        strings: strings.json dict (with RBAC permissions)
        app_name: App display name
        media_type: App type
        app_config: Optional app_config.json data
        
    Returns:
        HTML string (~12KB instead of ~194KB)
    """
    # Build RBAC matrix from strings.json
    by_id = strings.get("by_id", {})
    rbac_matrix = {}
    for code, info in by_id.items():
        perms = info.get("permissions")
        if perms:
            rbac_matrix[code] = perms
    
    # Build dataset tabs
    datasets = config.get("datasets", [])
    # Filter out _meta
    visible_datasets = [ds for ds in datasets if ds["name"] != "_meta"]
    first_ds = visible_datasets[0]["name"] if visible_datasets else "data"
    
    # Embed data
    embedded_config = json.dumps(config, ensure_ascii=False)
    embedded_strings = json.dumps(strings, ensure_ascii=False)
    embedded_rbac = json.dumps(rbac_matrix, ensure_ascii=False)
    embedded_app_config = json.dumps(app_config or {}, ensure_ascii=False)
    
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="theme-color" content="#0f0f1e">
<title>{app_name}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}}
body{{background:#0f0f1e;color:#f5f5f5;font-family:-apple-system,sans-serif;font-size:14px;overflow:hidden;display:flex;flex-direction:column;height:100dvh}}
.topbar{{display:flex;align-items:center;justify-content:space-between;padding:14px 16px;padding-top:max(14px,env(safe-area-inset-top));background:linear-gradient(135deg,#1a1a2e,#16213e);flex-shrink:0}}
.topbar-title{{flex:1;text-align:center;font-size:17px;font-weight:700;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding:0 12px}}
.topbar-icons{{display:flex;gap:8px}}
.icon-btn{{width:38px;height:38px;border-radius:50%;display:flex;align-items:center;justify-content:center;cursor:pointer;border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.05)}}
.icon-btn:active{{transform:scale(.92)}}
.icon-btn svg{{width:20px;height:20px;fill:currentColor}}
.icon-btn.whatsapp{{color:#25D366;background:rgba(37,211,102,.12)}}
.icon-btn.rate{{color:#facc15;background:rgba(250,204,21,.12)}}
.icon-btn.privacy{{color:#58a6ff;background:rgba(88,166,255,.12)}}
.search-bar{{padding:10px 16px;background:#1a1a2e;flex-shrink:0}}
.search-bar input{{width:100%;background:#0f0f1e;color:#f5f5f5;border:1px solid #30363d;border-radius:8px;padding:10px 14px;font-size:13px}}
.search-bar input:focus{{outline:none;border-color:#e94560}}
.content{{flex:1;overflow-y:auto;padding:8px 12px;-webkit-overflow-scrolling:touch}}
.modal{{position:fixed;inset:0;background:rgba(0,0,0,.7);display:none;align-items:center;justify-content:center;padding:20px;z-index:998}}
.modal.show{{display:flex}}
.modal-content{{background:#1a1a2e;border-radius:14px;max-width:500px;width:100%;padding:24px;border:1px solid #30363d}}
.modal-content h2{{color:#e94560;margin-bottom:12px;font-size:18px}}
.modal-content p{{color:#8b949e;font-size:13px;line-height:1.7;margin-bottom:10px}}
.modal-close{{display:block;margin:20px auto 0;padding:10px 24px;background:#e94560;color:#fff;border:none;border-radius:8px;cursor:pointer}}
.toast{{position:fixed;bottom:30px;left:50%;transform:translateX(-50%);background:rgba(0,0,0,.85);color:#fff;padding:10px 16px;border-radius:8px;font-size:13px;z-index:1000;opacity:0;transition:.2s}}
.toast.show{{opacity:1}}
</style>
</head>
<body>

<!-- Top Bar -->
<div class="topbar">
  <div class="topbar-icons">
    <div class="icon-btn whatsapp" onclick="CoreEngine.native('share',{{title:'{app_name}',text:'Check out this app!'}})">
      <svg viewBox="0 0 24 24"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.149-.197.297-.767.967-.94 1.165-.173.198-.347.223-.644.074-.297-.149-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.074-.149-.669-1.611-.916-2.207-.242-.579-.487-.5-.669-.51l-.57-.01c-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.71.306 1.263.489 1.694.625.712.227 1.36.195 1.872.118.571-.085 1.758-.719 2.006-1.413.247-.694.247-1.289.173-1.413-.074-.124-.272-.198-.57-.347"/></svg>
    </div>
  </div>
  <div class="topbar-title" id="appTitle">{app_name}</div>
  <div class="topbar-icons">
    <div class="icon-btn rate" onclick="CoreEngine._notify('Rating coming soon!')">
      <svg viewBox="0 0 24 24"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
    </div>
    <div class="icon-btn privacy" onclick="document.getElementById('privacyModal').classList.add('show')">
      <svg viewBox="0 0 24 24"><path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm-2 16l-4-4 1.41-1.41L10 14.17l6.59-6.59L18 9l-8 8z"/></svg>
    </div>
  </div>
</div>

<!-- Search -->
<div class="search-bar">
  <input type="text" id="searchInput" placeholder="Search..." oninput="filterGrid(this.value)">
</div>

<!-- Content: Declarative Web Components -->
<div class="content">
  <data-tabs></data-tabs>
  <data-grid id="mainGrid" dataset="{first_ds}"></data-grid>
</div>

<!-- Privacy Modal -->
<div class="modal" id="privacyModal">
  <div class="modal-content">
    <h2>Privacy Policy</h2>
    <p><strong>{app_name}</strong> respects your privacy.</p>
    <p>This app stores data locally for offline access. No personal data is collected.</p>
    <button class="modal-close" onclick="document.getElementById('privacyModal').classList.remove('show')">Close</button>
  </div>
</div>

<div class="toast" id="toast"></div>

<!-- Embedded Data -->
<script id="embeddedConfig" type="application/json">{embedded_config}</script>
<script id="embeddedStrings" type="application/json">{embedded_strings}</script>
<script id="rbacMatrix" type="application/json">{embedded_rbac}</script>
<script id="embeddedAppConfig" type="application/json">{embedded_app_config}</script>

<!-- v3.0 Core Engine + Components + Service Worker -->
<script src="core_engine.js"></script>
<script src="components.js"></script>

<script>
// Search filter
function filterGrid(query) {{
  const grid = document.getElementById('mainGrid');
  if (grid._filter !== undefined) {{
    grid._filter = query.toLowerCase();
    grid._render();
  }}
}}

// Set document title
document.getElementById('appTitle').textContent = '{app_name}';
console.log('{app_name} v3.0 loaded — Web Components + Service Worker + RBAC Directives');
</script>
</body>
</html>'''


def render_template_v3_file(function_dir: Path, app_name: str = "Universal App",
                            media_type: str = "any") -> str:
    """Read config.json + strings.json and generate v3 template.html + copy JS files."""
    config = json.loads((function_dir / "config.json").read_text(encoding="utf-8"))
    strings = json.loads((function_dir / "strings.json").read_text(encoding="utf-8"))
    app_config = {}
    app_config_path = function_dir / "app_config.json"
    if app_config_path.exists():
        app_config = json.loads(app_config_path.read_text(encoding="utf-8"))
    
    html = render_template_v3(config, strings, app_name, media_type, app_config)
    
    # Write template.html
    (function_dir / "template.html").write_text(html, encoding="utf-8")
    
    # Copy core_engine.js + components.js + sw.js
    v2_dir = Path(__file__).parent
    for js_file in ["core_engine.js", "components.js", "sw.js"]:
        src = v2_dir / js_file
        if src.exists():
            (function_dir / js_file).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    
    print(f"[template_renderer_v3] Generated template.html ({len(html):,} chars) + core_engine.js + components.js + sw.js", flush=True)
    return html


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        if path.exists():
            html = render_template_v3_file(path, "Test App", "hospital")
            print(f"Generated: {len(html):,} chars (v3.0)")
