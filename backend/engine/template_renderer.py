"""
template_renderer.py — Dynamically generates template.html from strings.json.

This is NOT a static template. It reads the Execution Matrix (strings.json)
and the Map (config.json) produced by data_analyzer_v2.py, then injects
the View, Event, and OnCreate configurations for every 5-char ID.

The output is a complete, standalone HTML page that:
1. Renders tabs per dataset (from config.json)
2. Renders search + stats bars
3. Renders cards per item (using View config from strings.json)
4. Renders detail viewer (using OnCreate + Control from strings.json)
5. Wires up events (using Event config from strings.json)
6. Includes WhatsApp/Privacy/Rate top bar icons
7. Reads config.json + strings.json at runtime for dynamic rendering

Author: Principal Software Architect
Version: 2.0.0
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def render_template(config: dict, strings: dict, app_name: str = "Universal App",
                    media_type: str = "any", app_config: dict = None) -> str:
    """Generate a complete template.html from config + strings.
    
    Args:
        config: The config.json dict (The Map)
        strings: The strings.json dict (The Execution Matrix)
        app_name: The app display name
        media_type: The app type (hospital, supermarket, etc.)
        app_config: Optional app_config.json data to embed
        
    Returns:
        A complete HTML string
    """
    ids = config.get("ids", {})
    by_id = strings.get("by_id", {})
    datasets = config.get("datasets", [])
    project_id = config.get("project_id", "UniversalApp")
    
    # Build dataset tabs
    tabs_html = _build_tabs(datasets, media_type)
    
    # Build CSS for all widgets
    css = _build_css(ids, by_id)
    
    # Build JS: variables + events + control logic
    js_vars = _build_js_variables(ids, by_id)
    js_events = _build_js_events(ids, by_id)
    js_control = _build_js_control(ids, by_id)
    js_render = _build_js_render(config, strings)
    
    # Embed config + strings as JSON (read at runtime)
    embedded_config = json.dumps(config, ensure_ascii=False)
    embedded_strings = json.dumps(strings, ensure_ascii=False)
    embedded_app_config = json.dumps(app_config or {}, ensure_ascii=False)
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="theme-color" content="#0f0f1e">
<title>{app_name}</title>
<style>
{css}
</style>
</head>
<body>

<!-- Top Bar -->
<div class="topbar">
  <div class="topbar-icons">
    <div class="icon-btn whatsapp" onclick="openWhatsAppChannel()" title="WhatsApp Channel">
      <svg viewBox="0 0 24 24"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.149-.197.297-.767.967-.94 1.165-.173.198-.347.223-.644.074-.297-.149-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.074-.149-.669-1.611-.916-2.207-.242-.579-.487-.5-.669-.51l-.57-.01c-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.71.306 1.263.489 1.694.625.712.227 1.36.195 1.872.118.571-.085 1.758-.719 2.006-1.413.247-.694.247-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884"/></svg>
    </div>
  </div>
  <div class="topbar-title" id="appTitle">{app_name}</div>
  <div class="topbar-icons">
    <div class="icon-btn rate" onclick="rateApp()" title="Rate">
      <svg viewBox="0 0 24 24"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
    </div>
    <div class="icon-btn privacy" onclick="openPrivacy()" title="Privacy">
      <svg viewBox="0 0 24 24"><path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm-2 16l-4-4 1.41-1.41L10 14.17l6.59-6.59L18 9l-8 8z"/></svg>
    </div>
  </div>
</div>

<!-- Tab Bar -->
<div class="tab-bar" id="tabBar">{tabs_html}</div>

<!-- Stats Bar -->
<div class="stats-bar" id="statsBar">
  <div class="stat-pill">Total: <b id="statTotal">0</b></div>
</div>

<!-- Search -->
<div class="search-bar">
  <input type="text" id="searchInput" placeholder="Search..." oninput="renderItems()">
</div>

<!-- Item List -->
<div class="list-container" id="itemList"></div>

<!-- Detail Viewer -->
<div class="viewer" id="viewer">
  <div class="viewer-header">
    <button class="close-btn" onclick="closeViewer()">
      <svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
    </button>
    <div class="viewer-title" id="viewerTitle">-</div>
  </div>
  <div class="viewer-body" id="viewerBody"></div>
</div>

<!-- Privacy Modal -->
<div class="modal" id="privacyModal">
  <div class="modal-content">
    <h2>Privacy Policy</h2>
    <p><strong>{app_name}</strong> respects your privacy.</p>
    <p>This app stores data locally for offline access. No personal data is collected.</p>
    <button class="modal-close" onclick="closePrivacy()">Close</button>
  </div>
</div>

<div class="toast" id="toast"></div>

<!-- Embedded Data (read at runtime) -->
<script id="embeddedConfig" type="application/json">{embedded_config}</script>
<script id="embeddedStrings" type="application/json">{embedded_strings}</script>
<script id="embeddedAppConfig" type="application/json">{embedded_app_config}</script>

<script>
// ═════════════════════════════════════════════════════════════════
// RUNTIME: Read embedded config + strings
// ═════════════════════════════════════════════════════════════════
const APP_CONFIG = JSON.parse(document.getElementById('embeddedAppConfig').textContent);
const CONFIG = JSON.parse(document.getElementById('embeddedConfig').textContent);
const STRINGS = JSON.parse(document.getElementById('embeddedStrings').textContent);
const APP_NAME = "{app_name}";
const IDS = CONFIG.ids || {{}};
const BY_ID = STRINGS.by_id || {{}};
const DATASETS = CONFIG.datasets || [];

// ═════════════════════════════════════════════════════════════════
// VARIABLES (from OnCreate.Variables)
// ═════════════════════════════════════════════════════════════════
{js_vars}

// ═════════════════════════════════════════════════════════════════
// STATE
// ═════════════════════════════════════════════════════════════════
let activeDataset = 0;
let datasets = [];

// ═════════════════════════════════════════════════════════════════
// RENDERING
// ═════════════════════════════════════════════════════════════════
{js_render}

// ═════════════════════════════════════════════════════════════════
// EVENTS (from Event config)
// ═════════════════════════════════════════════════════════════════
{js_events}

// ═════════════════════════════════════════════════════════════════
// CONTROL LOGIC (from OnCreate.Control)
// ═════════════════════════════════════════════════════════════════
{js_control}

// ═════════════════════════════════════════════════════════════════
// ACTIONS
// ═════════════════════════════════════════════════════════════════
// WhatsApp channel URL — auto-injected from app_config (settingsPickCard)
// Default: the official channel. Override via app_config.whatsapp_channel_url
const WHATSAPP_CHANNEL_URL = (APP_CONFIG && APP_CONFIG.whatsapp_channel_url) || 'https://whatsapp.com/channel/0029VaijFIC5Ejxq4oG6wX0E';
const WHATSAPP_CONTACT_NUMBER = (APP_CONFIG && APP_CONFIG.whatsapp_contact_number) || '+967773458975';

function openWhatsAppChannel() {{
  // Try to open WhatsApp app directly via intent URI (Android)
  // If app is not installed, falls back to web URL
  const channelId = WHATSAPP_CHANNEL_URL.split('/').pop();
  // Android intent: opens WhatsApp app directly, falls back to web URL
  const intentUri = 'intent://channel/' + channelId + '#Intent;package=com.whatsapp;S.browser_fallback_url=' + encodeURIComponent(WHATSAPP_CHANNEL_URL) + ';end';
  window.location.href = intentUri;
}}
function contactWhatsApp() {{
  const msg = encodeURIComponent('Hi I am from your Systems');
  const num = WHATSAPP_CONTACT_NUMBER.replace(/[^0-9]/g, '');
  // Try WhatsApp app first, fallback to web
  const intentUri = 'intent://send/' + num + '#Intent;package=com.whatsapp;S.browser_fallback_url=' + encodeURIComponent('https://wa.me/' + num + '?text=' + msg) + ';end';
  window.location.href = intentUri;
}}
function shareWhatsApp() {{
  // Legacy: now opens the channel (kept for backwards compatibility)
  openWhatsAppChannel();
}}
function rateApp() {{ showToast('Rating coming soon!'); }}
function openPrivacy() {{ document.getElementById('privacyModal').classList.add('show'); }}
function closePrivacy() {{ document.getElementById('privacyModal').classList.remove('show'); }}
function closeViewer() {{ document.getElementById('viewer').classList.remove('show'); document.getElementById('viewerBody').innerHTML = ''; }}
function showToast(msg) {{
  const t = document.getElementById('toast'); t.textContent = msg;
  t.classList.add('show'); setTimeout(() => t.classList.remove('show'), 2000);
}}

// ═════════════════════════════════════════════════════════════════
// INIT
// ═════════════════════════════════════════════════════════════════
document.getElementById('appTitle').textContent = APP_NAME;
loadData();
renderTabs();
renderItems();
console.log(APP_NAME + ' loaded - ' + Object.keys(IDS).length + ' IDs, ' + datasets.length + ' datasets');
</script>
</body>
</html>'''
    return html


# ═══════════════════════════════════════════════════════════════════════════
# CSS BUILDER
# ═══════════════════════════════════════════════════════════════════════════

def _build_css(ids: dict, by_id: dict) -> str:
    """Generate CSS from widget types in strings.json."""
    return '''*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
:root{--bg:#0f0f1e;--surface:#1a1a2e;--surface2:#16213e;--accent:#e94560;--fg:#f5f5f5;--fg2:#a3a3c2;--fg3:#6b6b8a;--green:#16a34a;--gold:#facc15;--radius:14px;--font:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
html,body{height:100%;background:var(--bg);color:var(--fg);font-family:var(--font);font-size:14px;overflow:hidden}
body{display:flex;flex-direction:column;height:100dvh}
.topbar{display:flex;align-items:center;justify-content:space-between;padding:14px 16px;padding-top:max(14px,env(safe-area-inset-top));background:linear-gradient(135deg,#1a1a2e,#16213e);flex-shrink:0}
.topbar-title{flex:1;text-align:center;font-size:17px;font-weight:700;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding:0 12px}
.topbar-icons{display:flex;gap:8px}
.icon-btn{width:38px;height:38px;border-radius:50%;display:flex;align-items:center;justify-content:center;cursor:pointer;border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.05)}
.icon-btn:active{transform:scale(.92)}
.icon-btn svg{width:20px;height:20px;fill:currentColor}
.icon-btn.whatsapp{color:#25D366;background:rgba(37,211,102,.12);border-color:rgba(37,211,102,.3)}
.icon-btn.privacy{color:#58a6ff;background:rgba(88,166,255,.12);border-color:rgba(88,166,255,.3)}
.icon-btn.rate{color:#facc15;background:rgba(250,204,21,.12);border-color:rgba(250,204,21,.3)}
.tab-bar{display:flex;gap:4px;padding:8px 12px;background:var(--surface);overflow-x:auto;flex-shrink:0}
.tab-btn{flex-shrink:0;padding:8px 14px;border-radius:8px;border:1px solid var(--border,#30363d);background:#21262d;color:var(--fg2);font-size:12px;font-weight:600;cursor:pointer;white-space:nowrap}
.tab-btn.active{background:var(--accent);color:#fff}
.stats-bar{display:flex;gap:8px;padding:8px 16px;background:var(--surface);overflow-x:auto;flex-shrink:0}
.stat-pill{background:#21262d;padding:4px 12px;border-radius:12px;font-size:11px;color:var(--fg2);white-space:nowrap}
.stat-pill b{color:var(--accent)}
.search-bar{padding:10px 16px;background:var(--surface);flex-shrink:0}
.search-bar input{width:100%;background:var(--bg);color:var(--fg);border:1px solid #30363d;border-radius:8px;padding:10px 14px;font-size:13px}
.search-bar input:focus{outline:none;border-color:var(--accent)}
.list-container{flex:1;overflow-y:auto;padding:8px 12px;-webkit-overflow-scrolling:touch}
.section-header{padding:12px 4px 6px;font-size:11px;font-weight:600;color:var(--accent);text-transform:uppercase;position:sticky;top:0;background:var(--bg);z-index:5}
.item-card{display:flex;align-items:center;gap:12px;padding:12px;background:var(--surface);border-radius:10px;margin-bottom:6px;cursor:pointer;border:1px solid transparent;transition:.15s}
.item-card:active{background:var(--surface2);border-color:var(--accent)}
.item-icon{width:44px;height:44px;border-radius:8px;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:22px;background:rgba(233,69,96,.15)}
.item-info{flex:1;min-width:0}
.item-name{font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.item-meta{font-size:11px;color:var(--fg2);margin-top:3px;display:flex;gap:8px;flex-wrap:wrap}
.item-meta .price{color:var(--green);font-weight:600}
.item-meta .status{padding:1px 6px;border-radius:4px;font-size:10px}
.item-meta .status.ok{background:rgba(22,163,74,.2);color:var(--green)}
.item-meta .status.warn{background:rgba(250,204,21,.2);color:var(--gold)}
.item-meta .status.crit{background:rgba(248,81,73,.2);color:#f85149}
.viewer{position:fixed;inset:0;background:rgba(0,0,0,.95);z-index:999;display:none;flex-direction:column}
.viewer.show{display:flex}
.viewer-header{display:flex;align-items:center;gap:12px;padding:14px 16px;padding-top:max(14px,env(safe-area-inset-top));background:rgba(0,0,0,.8);color:#fff}
.viewer-title{flex:1;font-size:15px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.close-btn{width:36px;height:36px;border-radius:50%;border:none;background:rgba(255,255,255,.15);color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center}
.close-btn svg{width:20px;height:20px;fill:currentColor}
.viewer-body{flex:1;overflow:auto;padding:16px;background:#000}
.detail-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.detail-field{background:var(--surface);padding:10px 12px;border-radius:8px;border:1px solid #30363d}
.detail-field .label{font-size:10px;color:var(--fg3);text-transform:uppercase;margin-bottom:3px}
.detail-field .value{font-size:13px;color:var(--fg);font-weight:500;word-break:break-word}
.detail-field .value.accent{color:var(--accent)}
.detail-field .value.green{color:var(--green)}
.toast{position:fixed;bottom:30px;left:50%;transform:translateX(-50%);background:rgba(0,0,0,.85);color:#fff;padding:10px 16px;border-radius:8px;font-size:13px;z-index:1000;opacity:0;transition:.2s}
.toast.show{opacity:1}
.modal{position:fixed;inset:0;background:rgba(0,0,0,.7);display:none;align-items:center;justify-content:center;padding:20px;z-index:998}
.modal.show{display:flex}
.modal-content{background:var(--surface);border-radius:14px;max-width:500px;width:100%;padding:24px;border:1px solid #30363d}
.modal-content h2{color:var(--accent);margin-bottom:12px;font-size:18px}
.modal-content p{color:var(--fg2);font-size:13px;line-height:1.7;margin-bottom:10px}
.modal-close{display:block;margin:20px auto 0;padding:10px 24px;background:var(--accent);color:#fff;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer}'''


# ═══════════════════════════════════════════════════════════════════════════
# JS GENERATORS
# ═══════════════════════════════════════════════════════════════════════════

def _build_tabs(datasets: list, media_type: str) -> str:
    """Generate HTML for dataset tabs."""
    icons = {"patients":"\U0001f465","doctors":"\U0001fa7a","nurses":"\U0001f489",
             "medicines":"\U0001f48a","invoices":"\U0001f4b0","rooms":"\U0001f6cf\ufe0f",
             "products":"\U0001f4e6","staff":"\U0001f468\u200d\u2695\ufe0f","_meta":"\u2139\ufe0f"}
    tabs = []
    for i, ds in enumerate(datasets):
        name = ds.get("name", "data")
        icon = icons.get(name.lower(), "\U0001f4cb")
        count = ds.get("item_count", 0)
        active = "active" if i == 0 else ""
        tabs.append(f'<button class="tab-btn {active}" onclick="switchTab({i})">{icon} {name} ({count})</button>')
    return "".join(tabs)


def _build_js_variables(ids: dict, by_id: dict) -> str:
    """Generate JS variable declarations from OnCreate.Variables."""
    lines = []
    for code, info in ids.items():
        oncreate = by_id.get(code, {}).get("OnCreate", {})
        var_decl = oncreate.get("Variables", "")
        if var_decl:
            # Convert to JS: "String hfhcd = ''" → "let hfhcd = '';"
            js_var = var_decl.replace("String ", "let ").replace("int ", "let ").replace("double ", "let ").replace("boolean ", "let ").replace("bool ", "let ").replace("List ", "let ").replace("Map ", "let ").replace("var ", "let ")
            lines.append(js_var)
    return "\n".join(lines)


def _build_js_events(ids: dict, by_id: dict) -> str:
    """Generate JS event handler functions from Event config."""
    lines = []
    for code, info in ids.items():
        events = by_id.get(code, {}).get("Event", {})
        for event_name, handler in events.items():
            # Convert event name to function name
            func_name = handler.split("(")[0] if "(" in handler else handler
            if func_name.endswith("_validate"):
                lines.append(f"function {func_name}() {{ /* Validate {code} */ }}")
            elif func_name.endswith("_search"):
                lines.append(f"function {func_name}() {{ renderItems(); }}")
            elif func_name.endswith("_on_select"):
                lines.append(f"function {func_name}() {{ /* Selection changed for {code} */ }}")
            elif func_name.endswith("_toggle"):
                lines.append(f"function {func_name}() {{ /* Toggle {code} */ }}")
    return "\n".join(lines) if lines else "// No events"


def _build_js_control(ids: dict, by_id: dict) -> str:
    """Generate JS control logic from OnCreate.Control."""
    lines = []
    for code, info in ids.items():
        oncreate = by_id.get(code, {}).get("OnCreate", {})
        control = oncreate.get("Control", "")
        if control:
            lines.append(f"// Control for {code} ({info['original']}): {control}")
    return "\n".join(lines) if lines else "// No control logic"


def _build_js_render(config: dict, strings: dict) -> str:
    """Generate the main rendering JS functions."""
    datasets = config.get("datasets", [])
    ds_names = [ds["name"] for ds in datasets]
    
    return f'''function loadData() {{
  // Load data from embedded config
  datasets = DATASETS.map(ds => ({{
    name: ds.name,
    items: [],
  }}));
  // Populate items from strings.json values
  for (const [code, idInfo] of Object.entries(IDS)) {{
    const dsName = idInfo.dataset;
    const values = BY_ID[code]?.values || [];
    values.forEach(v => {{
      let ds = datasets.find(d => d.name === v.dataset);
      if (!ds) {{ ds = {{name: v.dataset, items: []}}; datasets.push(ds); }}
      if (!ds.items[v.item_index]) ds.items[v.item_index] = {{}};
      ds.items[v.item_index][idInfo.original] = v.text;
    }});
  }}
}}

function renderTabs() {{
  const bar = document.getElementById('tabBar');
  const icons = {{patients:'\\u{{1F465}}',doctors:'\\u{{1FA7A}}',nurses:'\\u{{1F489}}',medicines:'\\u{{1F48A}}',invoices:'\\u{{1F4B0}}',rooms:'\\u{{1F6CF}}\\u{{FE0F}}',products:'\\u{{1F4E6}}'}};
  bar.innerHTML = datasets.map((ds, i) => {{
    const icon = icons[ds.name?.toLowerCase?.()] || '\\u{{1F4CB}}';
    return '<button class="tab-btn ' + (i === activeDataset ? 'active' : '') + '" onclick="switchTab(' + i + ')">' + icon + ' ' + (ds.name||'Data') + ' (' + (ds.items?.length||0) + ')</button>';
  }}).join('');
}}

function switchTab(i) {{
  activeDataset = i;
  renderTabs();
  renderItems();
}}

function renderItems() {{
  const ds = datasets[activeDataset];
  if (!ds) return;
  const filter = (document.getElementById('searchInput').value || '').toLowerCase();
  let items = ds.items.filter(i => i && JSON.stringify(i).toLowerCase().includes(filter));
  document.getElementById('statTotal').textContent = items.length;
  const list = document.getElementById('itemList');
  if (!items.length) {{ list.innerHTML = '<div style="text-align:center;padding:40px;color:#6b6b8a">No items</div>'; return; }}
  
  // Group by first string/enum field
  let groupField = null;
  const sample = items[0] || {{}};
  for (const k of Object.keys(sample)) {{
    const code = Object.entries(IDS).find(([c, info]) => info.original === k)?.[0];
    if (code && IDS[code].type === 'Enum') {{ groupField = k; break; }}
  }}
  
  const groups = {{}};
  items.forEach(item => {{
    const g = groupField ? (item[groupField] || 'Other') : 'All';
    if (!groups[g]) groups[g] = [];
    groups[g].push(item);
  }});
  
  let html = '';
  for (const [groupName, groupItems] of Object.entries(groups)) {{
    html += '<div class="section-header">' + escHtml(groupName) + ' (' + groupItems.length + ')</div>';
    groupItems.forEach(item => {{
      const nameField = Object.keys(IDS).map(c => IDS[c].original).find(f => item[f] !== undefined && ['name','title','patient','doctor','product'].includes(f.toLowerCase())) || Object.keys(item)[0] || 'Item';
      const name = item[nameField] || 'Unknown';
      let meta = '';
      for (const [code, info] of Object.entries(IDS)) {{
        if (info.original === nameField) continue;
        const val = item[info.original];
        if (val === undefined || val === '') continue;
        if (['price','fee','cost'].includes(info.original.toLowerCase())) {{
          meta += '<span class="price">' + escHtml(String(val)) + '</span>';
        }} else if (['status','severity'].includes(info.original.toLowerCase())) {{
          const cls = /stable|paid|available|ok/i.test(val) ? 'ok' : /crit|urgent|pending/i.test(val) ? 'crit' : 'warn';
          meta += '<span class="status ' + cls + '">' + escHtml(String(val)) + '</span>';
        }} else {{
          meta += '<span style="color:#8b949e;font-size:10px">' + escHtml(String(val).slice(0,20)) + '</span>';
        }}
        if (meta.split('</span>').length > 4) break;
      }}
      const idx = ds.items.indexOf(item);
      html += '<div class="item-card" onclick="viewItem(' + activeDataset + ',' + idx + ')"><div class="item-icon">\\u{{1F4CB}}</div><div class="item-info"><div class="item-name">' + escHtml(String(name)) + '</div><div class="item-meta">' + meta + '</div></div></div>';
    }});
  }}
  list.innerHTML = html;
}}

function viewItem(dsIdx, itemIdx) {{
  const ds = datasets[dsIdx];
  if (!ds) return;
  const item = ds.items[itemIdx];
  if (!item) return;
  const nameField = Object.keys(IDS).map(c => IDS[c].original).find(f => item[f] !== undefined && ['name','title','patient','doctor','product'].includes(f.toLowerCase())) || Object.keys(item)[0] || 'Item';
  document.getElementById('viewerTitle').textContent = item[nameField] || 'Detail';
  let html = '<div class="detail-grid">';
  for (const [code, info] of Object.entries(IDS)) {{
    const val = item[info.original];
    if (val === undefined) continue;
    let cls = '';
    if (['price','fee','cost'].includes(info.original.toLowerCase())) cls = 'green';
    if (['phone','id','patient_id'].includes(info.original.toLowerCase())) cls = 'accent';
    html += '<div class="detail-field"><div class="label">' + escHtml(info.original) + '</div><div class="value ' + cls + '">' + escHtml(String(val)) + '</div></div>';
  }}
  html += '</div>';
  document.getElementById('viewerBody').innerHTML = html;
  document.getElementById('viewer').classList.add('show');
}}

function escHtml(s) {{ return (s||'').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}})[c]); }}'''


# ═══════════════════════════════════════════════════════════════════════════
# MAIN ENTRY
# ═══════════════════════════════════════════════════════════════════════════

def render_template_file(function_dir: Path, app_name: str = "Universal App",
                         media_type: str = "any") -> str:
    """Read config.json + strings.json from function_dir and generate template.html.
    
    Args:
        function_dir: Path containing config.json + strings.json
        app_name: App display name
        media_type: App type
        
    Returns:
        The generated HTML string (also writes to function_dir/template.html)
    """
    config_path = function_dir / "config.json"
    strings_path = function_dir / "strings.json"
    app_config_path = function_dir / "app_config.json"
    
    if not config_path.exists() or not strings_path.exists():
        raise FileNotFoundError("config.json or strings.json not found")
    
    config = json.loads(config_path.read_text(encoding="utf-8"))
    strings = json.loads(strings_path.read_text(encoding="utf-8"))
    app_config = json.loads(app_config_path.read_text(encoding="utf-8")) if app_config_path.exists() else {}
    
    html = render_template(config, strings, app_name, media_type, app_config)
    
    # Write to function_dir/template.html
    (function_dir / "template.html").write_text(html, encoding="utf-8")
    
    print(f"[template_renderer] Generated template.html ({len(html):,} chars, {len(config.get('ids',{}))} IDs)", flush=True)
    return html


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        if path.exists():
            html = render_template_file(path, "Test App", "hospital")
            print(f"Generated: {len(html):,} chars")
