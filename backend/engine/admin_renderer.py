"""
admin_renderer.py — Generates Admin.html (control panel) from config + strings.

Admin.html is a management interface that:
1. Lists all 5-char IDs with their original names, types, and builders
2. Allows editing the View, Event, and OnCreate config per ID
3. Integrates GrapesJS (visual layout editor)
4. Integrates Blockly (block-based logic editor)
5. Integrates Fabric.js (canvas/graphic editor)
6. Exports updated config.json + strings.json

Author: Principal Software Architect
Version: 2.0.0
"""
from __future__ import annotations

import json
from pathlib import Path


def render_admin(config: dict, strings: dict, app_name: str = "Admin Panel") -> str:
    """Generate Admin.html from config + strings.
    
    Args:
        config: The config.json dict
        strings: The strings.json dict
        app_name: App name for the panel
        
    Returns:
        Complete HTML string for Admin.html
    """
    ids = config.get("ids", {})
    by_id = strings.get("by_id", {})
    datasets = config.get("datasets", [])
    
    # Build ID table rows
    id_rows = []
    for code, info in ids.items():
        view = by_id.get(code, {}).get("View", {})
        events = by_id.get(code, {}).get("Event", {})
        oncreate = by_id.get(code, {}).get("OnCreate", {})
        
        builders_html = "".join(f'<span class="builder-tag">{b}</span>' for b in info.get("builders", []))
        events_html = "".join(f'<span class="event-tag">{e}</span>' for e in events.keys()) if events else '<span class="muted">none</span>'
        
        id_rows.append(f'''<tr class="id-row" data-code="{code}" onclick="editId('{code}')">
          <td class="code-cell">{code}</td>
          <td>{info.get('original', '')}</td>
          <td><span class="type-tag type-{info.get('type','').lower()}">{info.get('type', '')}</span></td>
          <td><span class="widget-tag">{info.get('widget', '')}</span></td>
          <td>{builders_html}</td>
          <td>{events_html}</td>
          <td><span class="ds-tag">{info.get('dataset', '')}</span></td>
        </tr>''')
    
    id_table = "\n".join(id_rows)
    
    # Dataset summary
    ds_cards = []
    for ds in datasets:
        ds_cards.append(f'''<div class="ds-card">
          <div class="ds-icon">{_ds_icon(ds.get('name',''))}</div>
          <div class="ds-info"><div class="ds-name">{ds.get('name','')}</div>
          <div class="ds-meta">{ds.get('item_count',0)} items &middot {len(ds.get('fields',[]))} fields</div></div>
        </div>''')
    ds_html = "\n".join(ds_cards)
    
    embedded_config = json.dumps(config, ensure_ascii=False)
    embedded_strings = json.dumps(strings, ensure_ascii=False)
    
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{app_name} - Admin</title>

<!-- GrapesJS CSS -->
<link rel="stylesheet" href="https://unpkg.com/grapesjs/dist/css/grapes.min.css">

<!-- Blockly -->
<script src="https://unpkg.com/blockly/blockly.min.js"></script>

<!-- Fabric.js -->
<script src="https://unpkg.com/fabric@5.3.0/dist/fabric.min.js"></script>

<style>
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{--bg:#0d1117;--surface:#161b22;--surface2:#21262d;--border:#30363d;--fg:#e6edf3;--fg2:#8b949e;--accent:#58a6ff;--green:#3fb950;--orange:#d29922;--red:#f85149;--purple:#bc8cff}}
body{{background:var(--bg);color:var(--fg);font-family:-apple-system,sans-serif;font-size:14px;padding:16px}}
h1{{font-size:20px;color:var(--accent);margin-bottom:4px}}
.sub{{color:var(--fg2);font-size:12px;margin-bottom:20px}}
.stats-row{{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}}
.stat{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:10px 16px;font-size:12px;color:var(--fg2)}}
.stat b{{color:var(--accent);font-size:18px;display:block}}
.ds-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:8px;margin-bottom:20px}}
.ds-card{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:12px;display:flex;align-items:center;gap:10px}}
.ds-icon{{font-size:24px}}
.ds-name{{font-weight:600;font-size:13px}}
.ds-meta{{font-size:11px;color:var(--fg2);margin-top:2px}}
.section-title{{font-size:14px;font-weight:700;color:var(--accent);margin:20px 0 10px;border-bottom:1px solid var(--border);padding-bottom:6px}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
th{{text-align:left;padding:8px;background:var(--surface2);border-bottom:2px solid var(--border);font-size:11px;text-transform:uppercase;color:var(--fg2)}}
td{{padding:8px;border-bottom:1px solid var(--border)}}
tr.id-row{{cursor:pointer;transition:.15s}}
tr.id-row:hover{{background:var(--surface2)}}
.code-cell{{font-family:monospace;color:var(--purple);font-weight:600}}
.type-tag,.widget-tag,.ds-tag{{padding:2px 8px;border-radius:4px;font-size:10px}}
.type-tag{{background:rgba(88,166,255,.15);color:var(--accent)}}
.type-enum{{background:rgba(188,140,255,.15);color:var(--purple)}}
.type-int,.type-float{{background:rgba(63,185,80,.15);color:var(--green)}}
.type-boolean{{background:rgba(210,153,34,.15);color:var(--orange)}}
.type-canvas{{background:rgba(248,81,73,.15);color:var(--red)}}
.widget-tag{{background:var(--surface2);color:var(--fg2)}}
.ds-tag{{background:rgba(63,185,80,.15);color:var(--green);font-family:monospace;font-size:10px}}
.builder-tag{{display:inline-block;background:var(--surface2);padding:1px 6px;border-radius:3px;font-size:9px;color:var(--fg2);margin:1px}}
.event-tag{{display:inline-block;background:rgba(210,153,34,.15);padding:1px 6px;border-radius:3px;font-size:9px;color:var(--orange);margin:1px}}
.muted{{color:var(--fg2);font-style:italic}}
.btn{{background:var(--accent);color:#fff;border:none;padding:8px 16px;border-radius:6px;font-size:12px;cursor:pointer;margin:4px}}
.btn:hover{{opacity:.9}}
.btn-alt{{background:var(--surface2);color:var(--fg);border:1px solid var(--border)}}
.btn-row{{margin:16px 0}}
/* Edit modal */
.edit-modal{{position:fixed;inset:0;background:rgba(0,0,0,.8);display:none;align-items:center;justify-content:center;z-index:1000;padding:20px}}
.edit-modal.show{{display:flex}}
.edit-content{{background:var(--surface);border-radius:12px;max-width:600px;width:100%;max-height:80vh;overflow:auto;padding:24px;border:1px solid var(--border)}}
.edit-content h2{{color:var(--accent);margin-bottom:12px}}
.edit-field{{margin-bottom:12px}}
.edit-field label{{display:block;font-size:11px;color:var(--fg2);margin-bottom:4px}}
.edit-field input,.edit-field select,.edit-field textarea{{width:100%;background:var(--bg);color:var(--fg);border:1px solid var(--border);border-radius:6px;padding:8px;font-size:13px}}
.edit-field textarea{{min-height:80px;font-family:monospace;font-size:11px}}
/* GrapesJS container */
#grapesjs-container{{height:400px;border:1px solid var(--border);border-radius:8px;margin:12px 0;display:none}}
#grapesjs-container.show{{display:block}}
/* Blockly container */
#blockly-container{{height:300px;border:1px solid var(--border);border-radius:8px;margin:12px 0;display:none}}
#blockly-container.show{{display:block}}
/* Fabric canvas */
#fabric-container{{display:none;margin:12px 0}}
#fabric-container.show{{display:block}}
#fabric-canvas{{border:1px solid var(--border);border-radius:8px}}
</style>
</head>
<body>

<h1>🔧 {app_name} - Admin Panel</h1>
<div class="sub">Project: {config.get('project_id','')} | {config.get('total_ids',0)} IDs | {config.get('total_datasets',0)} datasets | {config.get('total_items',0)} items</div>

<div class="stats-row">
  <div class="stat"><b>{config.get('total_ids',0)}</b>Unique IDs</div>
  <div class="stat"><b>{config.get('total_datasets',0)}</b>Datasets</div>
  <div class="stat"><b>{config.get('total_items',0)}</b>Total Items</div>
  <div class="stat"><b>{len(set(info.get('type','') for info in ids.values()))}</b>Type Variants</div>
</div>

<div class="section-title">📊 Datasets</div>
<div class="ds-grid">{ds_html}</div>

<div class="section-title">🧩 ID Registry (Click to Edit)</div>
<table>
  <thead><tr><th>Code</th><th>Original</th><th>Type</th><th>Widget</th><th>Builders</th><th>Events</th><th>Dataset</th></tr></thead>
  <tbody>
    {id_table}
  </tbody>
</table>

<div class="btn-row">
  <button class="btn" onclick="toggleGrapesJS()">🎨 GrapesJS Editor</button>
  <button class="btn btn-alt" onclick="toggleBlockly()">🧱 Blockly Logic</button>
  <button class="btn btn-alt" onclick="toggleFabric()">🖼️ Fabric.js Canvas</button>
  <button class="btn" onclick="exportConfig()">⬇ Export config.json</button>
  <button class="btn" onclick="exportStrings()">⬇ Export strings.json</button>
</div>

<!-- GrapesJS Container -->
<div id="grapesjs-container"></div>

<!-- Blockly Container -->
<div id="blockly-container">
  <div id="blockly-div" style="width:100%;height:100%"></div>
  <xml id="blockly-toolbox" style="display:none">
    <block type="controls_if"></block>
    <block type="logic_compare"></block>
    <block type="math_number"></block>
    <block type="text"></block>
    <block type="variables_get"></block>
    <block type="variables_set"></block>
  </xml>
</div>

<!-- Fabric.js Container -->
<div id="fabric-container">
  <canvas id="fabric-canvas" width="560" height="300"></canvas>
</div>

<!-- Edit Modal -->
<div class="edit-modal" id="editModal">
  <div class="edit-content">
    <h2 id="editTitle">Edit ID</h2>
    <div class="edit-field">
      <label>5-Char Code</label>
      <input type="text" id="editCode" readonly>
    </div>
    <div class="edit-field">
      <label>Original Name</label>
      <input type="text" id="editOriginal" readonly>
    </div>
    <div class="edit-field">
      <label>Widget Type</label>
      <select id="editWidget">
        <option>EditText</option><option>TextView</option><option>Spinner</option>
        <option>Switch</option><option>ImageView</option><option>DatePicker</option>
        <option>RecyclerView</option><option>CardView</option>
      </select>
    </div>
    <div class="edit-field">
      <label>Route</label>
      <input type="text" id="editRoute">
    </div>
    <div class="edit-field">
      <label>View Config (JSON)</label>
      <textarea id="editView"></textarea>
    </div>
    <div class="edit-field">
      <label>Event Config (JSON)</label>
      <textarea id="editEvent"></textarea>
    </div>
    <div class="edit-field">
      <label>OnCreate Config (JSON)</label>
      <textarea id="editOnCreate"></textarea>
    </div>
    <div class="btn-row">
      <button class="btn" onclick="saveEdit()">Save</button>
      <button class="btn btn-alt" onclick="closeEdit()">Cancel</button>
    </div>
  </div>
</div>

<!-- Embedded Data -->
<script id="adminConfig" type="application/json">{embedded_config}</script>
<script id="adminStrings" type="application/json">{embedded_strings}</script>

<script>
const CONFIG = JSON.parse(document.getElementById('adminConfig').textContent);
const STRINGS = JSON.parse(document.getElementById('adminStrings').textContent);
let editor = null;

// ═════════════════════════════════════════════════════════════════
// EDIT MODAL
// ═════════════════════════════════════════════════════════════════
function editId(code) {{
  const info = CONFIG.ids[code];
  const str = STRINGS.by_id[code] || {{}};
  document.getElementById('editTitle').textContent = 'Edit: ' + code + ' (' + info.original + ')';
  document.getElementById('editCode').value = code;
  document.getElementById('editOriginal').value = info.original;
  document.getElementById('editWidget').value = info.widget || 'EditText';
  document.getElementById('editRoute').value = str.route || '';
  document.getElementById('editView').value = JSON.stringify(str.View || {{}}, null, 2);
  document.getElementById('editEvent').value = JSON.stringify(str.Event || {{}}, null, 2);
  document.getElementById('editOnCreate').value = JSON.stringify(str.OnCreate || {{}}, null, 2);
  document.getElementById('editModal').classList.add('show');
}}

function closeEdit() {{ document.getElementById('editModal').classList.remove('show'); }}

function saveEdit() {{
  const code = document.getElementById('editCode').value;
  const widget = document.getElementById('editWidget').value;
  const route = document.getElementById('editRoute').value;
  try {{
    const view = JSON.parse(document.getElementById('editView').value || '{{}}');
    const event = JSON.parse(document.getElementById('editEvent').value || '{{}}');
    const oncreate = JSON.parse(document.getElementById('editOnCreate').value || '{{}}');
    if (!STRINGS.by_id[code]) STRINGS.by_id[code] = {{}};
    CONFIG.ids[code].widget = widget;
    STRINGS.by_id[code].route = route;
    STRINGS.by_id[code].View = view;
    STRINGS.by_id[code].Event = event;
    STRINGS.by_id[code].OnCreate = oncreate;
    closeEdit();
    alert('Saved: ' + code);
  }} catch(e) {{ alert('JSON parse error: ' + e.message); }}
}}

// ═════════════════════════════════════════════════════════════════
// GRAPESJS
// ═════════════════════════════════════════════════════════════════
function toggleGrapesJS() {{
  const c = document.getElementById('grapesjs-container');
  c.classList.toggle('show');
  if (c.classList.contains('show') && !editor) {{
    if (typeof grapesjs !== 'undefined') {{
      editor = grapesjs.init({{
        container: '#grapesjs-container',
        components: '<div class="admin-layout">Drag components here</div>',
        style: '.admin-layout{{padding:20px;min-height:200px;background:#fff}}',
      }});
      console.log('GrapesJS initialized');
    }} else {{
      c.innerHTML = '<p style="padding:20px;color:#8b949e">GrapesJS loaded from CDN. If not visible, check network connection.</p>';
    }}
  }}
}}

// ═════════════════════════════════════════════════════════════════
// BLOCKLY
// ═════════════════════════════════════════════════════════════════
let blocklyWorkspace = null;
function toggleBlockly() {{
  const c = document.getElementById('blockly-container');
  c.classList.toggle('show');
  if (c.classList.contains('show') && !blocklyWorkspace) {{
    if (typeof Blockly !== 'undefined') {{
      blocklyWorkspace = Blockly.inject('blockly-div', {{
        toolbox: document.getElementById('blockly-toolbox'),
        trashcan: true,
      }});
      console.log('Blockly initialized');
    }} else {{
      c.innerHTML = '<p style="padding:20px;color:#8b949e">Blockly loaded from CDN. If not visible, check network.</p>';
    }}
  }}
}}

// ═════════════════════════════════════════════════════════════════
// FABRIC.JS
// ═════════════════════════════════════════════════════════════════
let fabricCanvas = null;
function toggleFabric() {{
  const c = document.getElementById('fabric-container');
  c.classList.toggle('show');
  if (c.classList.contains('show') && !fabricCanvas) {{
    if (typeof fabric !== 'undefined') {{
      fabricCanvas = new fabric.Canvas('fabric-canvas');
      fabricCanvas.backgroundColor = '#1a1a2e';
      fabricCanvas.renderAll();
      // Add a test rectangle
      const rect = new fabric.Rect({{left:50, top:50, width:100, height:60, fill:'#e94560', rx:8}});
      fabricCanvas.add(rect);
      console.log('Fabric.js initialized');
    }} else {{
      c.innerHTML = '<p style="padding:20px;color:#8b949e">Fabric.js loaded from CDN. If not visible, check network.</p>';
    }}
  }}
}}

// ═════════════════════════════════════════════════════════════════
// EXPORT
// ═════════════════════════════════════════════════════════════════
function exportConfig() {{
  const blob = new Blob([JSON.stringify(CONFIG, null, 2)], {{type: 'application/json'}});
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
  a.download = 'config.json'; a.click();
}}
function exportStrings() {{
  const blob = new Blob([JSON.stringify(STRINGS, null, 2)], {{type: 'application/json'}});
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
  a.download = 'strings.json'; a.click();
}}

console.log('Admin panel loaded: ' + Object.keys(CONFIG.ids).length + ' IDs');
</script>
</body>
</html>'''


def _ds_icon(name: str) -> str:
    icons = {"patients":"\U0001f465","doctors":"\U0001fa7a","nurses":"\U0001f489",
             "medicines":"\U0001f48a","invoices":"\U0001f4b0","rooms":"\U0001f6cf\ufe0f",
             "products":"\U0001f4e6","staff":"\U0001f468\u200d\u2695\ufe0f","_meta":"\u2139\ufe0f"}
    return icons.get(name.lower(), "\U0001f4cb")


def render_admin_file(function_dir: Path, app_name: str = "Admin Panel") -> str:
    """Read config.json + strings.json and generate Admin.html."""
    config = json.loads((function_dir / "config.json").read_text(encoding="utf-8"))
    strings = json.loads((function_dir / "strings.json").read_text(encoding="utf-8"))
    
    html = render_admin(config, strings, app_name)
    (function_dir / "Admin.html").write_text(html, encoding="utf-8")
    
    print(f"[admin_renderer] Generated Admin.html ({len(html):,} chars)", flush=True)
    return html


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        if path.exists():
            html = render_admin_file(path, "Test Admin")
            print(f"Generated: {len(html):,} chars")
