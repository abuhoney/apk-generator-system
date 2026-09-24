"""
data_analyzer_v2.py — Deep Data Analysis Engine for the Dynamic Template System.

This is NOT a simple field extractor. It is a Code Generation Intelligence Engine that:
1. Parses ANY file (JSON, CSV, TXT, HTML, Excel, PDF, Word)
2. Extracts DOM elements, data fields, events, and structural metadata
3. Assigns a unique 5-char alphanumeric hash (Isolation ID) to every entity
4. Generates a deep config.json (The Map) with type info + builder assignments
5. Generates a deep strings.json (The Execution Matrix) with View, Event, OnCreate per ID

The output files are consumed by the 10 Builders (Factory Pattern) to dynamically
generate template.html (user UI) and Admin.html (control panel).

Author: Principal Software Architect
Version: 2.0.0
"""
from __future__ import annotations

import json
import hashlib
import datetime
import re
from pathlib import Path
from typing import Any, Optional


# ═══════════════════════════════════════════════════════════════════════════
# 1. CORE: 5-CHARACTER ID GENERATOR (Isolation System)
# ═══════════════════════════════════════════════════════════════════════════

# Charset: lowercase letters + digits (36 chars) → 36^5 = 60,466,176 unique IDs
_CHARSET = "abcdefghijklmnopqrstuvwxyz0123456789"
_USED_CODES: set[str] = set()  # Ensures global uniqueness within a session


def generate_code(entity_name: str, salt: int = 0) -> str:
    """Generate a deterministic, unique 5-character alphanumeric code.
    
    Uses MD5 hash of (entity_name + salt) for determinism.
    If a collision occurs, increments salt until a unique code is found.
    
    Args:
        entity_name: The original field/element/variable name
        salt: Optional salt for collision resolution
        
    Returns:
        A unique 5-character string (e.g., "hfhcd", "gdygd")
    """
    global _USED_CODES
    while True:
        h = hashlib.md5(f"{entity_name}_{salt}".encode()).digest()
        code = ""
        for b in h[:5]:
            code += _CHARSET[b % len(_CHARSET)]
        if code not in _USED_CODES:
            _USED_CODES.add(code)
            return code
        salt += 1  # Collision → try next salt


# ═══════════════════════════════════════════════════════════════════════════
# 2. FIELD TYPE DETECTION (Smart Type Inference)
# ═══════════════════════════════════════════════════════════════════════════

def detect_type(value: Any, field_name: str = "") -> dict:
    """Infer the type and metadata of a field value.
    
    Returns a dict with:
        - "type": Base type (String, Int, Float, Boolean, Array, Object, Canvas, Null)
        - "widget": Suggested Android/widget type
        - "input_type": HTML input type
        - "builders": Which builders should process this field
    """
    if value is None:
        return {"type": "Null", "widget": "TextView", "input_type": "text", "builders": ["View"]}
    
    if isinstance(value, bool):
        return {"type": "Boolean", "widget": "Switch", "input_type": "checkbox",
                "builders": ["Variables", "View", "Control", "Operator"]}
    
    if isinstance(value, int):
        return {"type": "Int", "widget": "EditText", "input_type": "number",
                "builders": ["Variables", "View", "Math", "Operator"]}
    
    if isinstance(value, float):
        return {"type": "Float", "widget": "EditText", "input_type": "number",
                "builders": ["Variables", "View", "Math", "Operator"]}
    
    if isinstance(value, list):
        return {"type": "Array", "widget": "RecyclerView", "input_type": "list",
                "builders": ["List", "View", "Component", "Control"]}
    
    if isinstance(value, dict):
        return {"type": "Object", "widget": "CardView", "input_type": "object",
                "builders": ["Component", "View"]}
    
    if isinstance(value, str):
        # Check for special string types
        lower_val = str(value).lower()
        lower_name = field_name.lower()
        
        # URL detection
        if lower_val.startswith(("http://", "https://")):
            return {"type": "URL", "widget": "ImageView", "input_type": "url",
                    "builders": ["View", "File", "Component"]}
        
        # Email detection
        if "@" in lower_val and "." in lower_val:
            return {"type": "Email", "widget": "EditText", "input_type": "email",
                    "builders": ["Variables", "View", "Operator"]}
        
        # Phone detection
        if re.match(r'^\+?[\d\s\-()]+$', lower_val) and len(lower_val) >= 7:
            return {"type": "Phone", "widget": "EditText", "input_type": "tel",
                    "builders": ["Variables", "View", "Operator"]}
        
        # Date detection
        if re.match(r'^\d{4}-\d{2}-\d{2}', lower_val):
            return {"type": "Date", "widget": "DatePicker", "input_type": "date",
                    "builders": ["Variables", "View", "Math"]}
        
        # Image base64 detection
        if lower_val.startswith("data:image") or (len(value) > 100 and re.match(r'^[A-Za-z0-9+/=]+$', value)):
            return {"type": "Canvas", "widget": "ImageView", "input_type": "image",
                    "builders": ["View", "Math", "File", "Component"]}
        
        # Status/enum detection (short strings that repeat)
        if len(value) <= 30 and lower_name in ("status", "type", "category", "severity", "gender", "shift", "role"):
            return {"type": "Enum", "widget": "Spinner", "input_type": "select",
                    "builders": ["Variables", "View", "Control", "List"]}
        
        # Default: plain string
        return {"type": "String", "widget": "EditText", "input_type": "text",
                "builders": ["Variables", "View"]}
    
    return {"type": "String", "widget": "EditText", "input_type": "text", "builders": ["View"]}


# ═══════════════════════════════════════════════════════════════════════════
# 3. FILE PARSERS (Universal Ingestion)
# ═══════════════════════════════════════════════════════════════════════════

def parse_json_file(content: str, filename: str) -> list:
    """Parse JSON content into datasets."""
    data = json.loads(content)
    datasets = []
    
    if isinstance(data, list):
        datasets.append({"name": _clean_name(filename), "items": data})
        return datasets
    
    if not isinstance(data, dict):
        return datasets
    
    # Check for "data" wrapper (common in our project)
    if "data" in data and isinstance(data["data"], dict):
        # Extract project-level metadata
        meta = {k: v for k, v in data.items() if k != "data" and not isinstance(v, (list, dict))}
        if meta:
            datasets.append({"name": "_meta", "items": [meta]})
        for key, val in data["data"].items():
            if isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict):
                datasets.append({"name": key, "items": val})
        return datasets
    
    # Check for direct array values
    found = False
    for key, val in data.items():
        if isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict):
            datasets.append({"name": key, "items": val})
            found = True
    if found:
        return datasets
    
    # Single object
    datasets.append({"name": _clean_name(filename), "items": [data]})
    return datasets


def parse_csv_file(content: str, filename: str) -> list:
    """Parse CSV content into a dataset."""
    lines = content.strip().split("\n")
    if len(lines) < 2:
        return []
    headers = [h.strip() for h in lines[0].split(",")]
    items = []
    for line in lines[1:]:
        vals = line.split(",")
        item = {}
        for i, h in enumerate(headers):
            v = vals[i].strip() if i < len(vals) else ""
            try:
                v = int(v)
            except ValueError:
                try:
                    v = float(v)
                except ValueError:
                    pass
            item[h] = v
        items.append(item)
    return [{"name": _clean_name(filename), "items": items}]


def parse_txt_file(content: str, filename: str) -> list:
    """Parse TXT content (key: value format or plain lines)."""
    items = []
    for line in content.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            items.append({"name": k.strip(), "value": v.strip()})
        else:
            items.append({"name": line})
    return [{"name": _clean_name(filename), "items": items}]


def parse_html_file(content: str, filename: str) -> list:
    """Parse HTML content — extract DOM elements as data items."""
    items = []
    # Extract IDs
    for m in re.finditer(r'id="([^"]+)"', content):
        items.append({"tag": "element", "id": m.group(1), "type": "DOM_ID"})
    # Extract classes
    for m in re.finditer(r'class="([^"]+)"', content):
        items.append({"tag": "element", "class": m.group(1), "type": "DOM_CLASS"})
    # Extract data attributes
    for m in re.finditer(r'data-([a-z-]+)="([^"]+)"', content):
        items.append({"tag": "data", "attr": m.group(1), "value": m.group(2), "type": "DATA_ATTR"})
    if not items:
        items.append({"content": content[:500], "type": "RAW_HTML"})
    return [{"name": _clean_name(filename), "items": items}]


def _clean_name(filename: str) -> str:
    """Clean a filename into a dataset name."""
    name = re.sub(r'\.[^.]+$', '', filename)  # Remove extension
    name = name.replace('_', ' ').replace('-', ' ')
    return name.title() if name else "Data"


# ═══════════════════════════════════════════════════════════════════════════
# 4. CONFIG.JSON GENERATOR (The Map)
# ═══════════════════════════════════════════════════════════════════════════

def build_config(datasets: list, project_name: str = "UniversalApp") -> dict:
    """Build the deep config.json (The Map) from parsed datasets.
    
    Structure:
    {
        "project_id": "...",
        "generated_at": "...",
        "ids": {
            "hfhcd": {"original": "patient_name", "type": "String", "builders": [...], "dataset": "..."},
            ...
        },
        "datasets": [...],
        "codes_index": {"hfhcd": "patient_name", ...},  # Reverse lookup
    }
    """
    ids = {}
    codes_index = {}
    dataset_summaries = []
    
    for ds in datasets:
        ds_name = ds["name"]
        ds_items = ds["items"]
        ds_fields = []
        seen_fields = set()
        
        for item in ds_items:
            if not isinstance(item, dict):
                continue
            for field_name, value in item.items():
                if field_name in seen_fields:
                    continue
                seen_fields.add(field_name)
                
                type_info = detect_type(value, field_name)
                code = generate_code(field_name)
                
                ids[code] = {
                    "original": field_name,
                    "type": type_info["type"],
                    "widget": type_info["widget"],
                    "input_type": type_info["input_type"],
                    "builders": type_info["builders"],
                    "dataset": ds_name,
                    "sample_value": _truncate_sample(value),
                }
                codes_index[code] = field_name
                ds_fields.append({"field": field_name, "code": code, "type": type_info["type"]})
        
        dataset_summaries.append({
            "name": ds_name,
            "item_count": len(ds_items),
            "fields": ds_fields,
        })
    
    config = {
        "project_id": project_name.upper().replace(" ", "_")[:20],
        "generated_at": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "total_ids": len(ids),
        "total_datasets": len(datasets),
        "total_items": sum(len(ds["items"]) for ds in datasets),
        "ids": ids,
        "datasets": dataset_summaries,
        "codes_index": codes_index,
    }
    
    print(f"[data_analyzer_v2] config.json: {len(ids)} IDs, {len(datasets)} datasets, {config['total_items']} items", flush=True)
    return config


def _truncate_sample(value: Any, max_len: int = 100) -> str:
    """Truncate a sample value for display in config.json."""
    s = str(value)
    return s[:max_len] + "..." if len(s) > max_len else s


# ═══════════════════════════════════════════════════════════════════════════
# 5. STRINGS.JSON GENERATOR (The Execution Matrix)
# ═══════════════════════════════════════════════════════════════════════════

def build_strings(config: dict, datasets: list) -> dict:
    """Build the deep strings.json (The Execution Matrix) from config + datasets.
    
    For each 5-char ID, generates:
    {
        "hfhcd": {
            "Code": "EditText",           # Widget type
            "route": "patient/registration", # Navigation route
            "View": {                      # View configuration
                "layout": "...",
                "widget": "...",
                "libraries": [...],
                "properties": {...}
            },
            "Event": {                     # Event handlers
                "onTextChanged": "...",
                "onSubmit": "...",
                "onClick": "..."
            },
            "OnCreate": {                  # Initialization logic
                "Variables": "...",
                "Control": "...",
                "MoreBlock": "..."
            }
        }
    }
    """
    strings = {}
    ids = config["ids"]
    
    for code, id_info in ids.items():
        original = id_info["original"]
        id_type = id_info["type"]
        widget = id_info["widget"]
        dataset = id_info["dataset"]
        
        # Determine route from dataset + field
        route = f"{dataset.lower()}/{original.lower().replace(' ', '_')}"
        
        # Determine libraries based on widget type
        libraries = _get_libraries(widget)
        
        # Determine layout based on type
        layout = _get_layout(id_type)
        
        # Determine properties
        properties = _get_properties(original, id_type, id_info.get("sample_value", ""))
        
        # Determine events based on type
        events = _get_events(code, original, id_type)
        
        # Determine OnCreate logic
        oncreate = _get_oncreate(code, original, id_type, dataset)
        
        strings[code] = {
            "Code": widget,
            "route": route,
            "View": {
                "layout": layout,
                "widget": widget,
                "libraries": libraries,
                "properties": properties,
            },
            "Event": events,
            "OnCreate": oncreate,
            "values": [],  # Will be filled with actual data values
        }
    
    # Fill in actual data values from datasets
    for ds in datasets:
        ds_name = ds["name"]
        for item_idx, item in enumerate(ds["items"]):
            if not isinstance(item, dict):
                continue
            for field_name, value in item.items():
                # Find the code for this field
                for code, id_info in ids.items():
                    if id_info["original"] == field_name and id_info["dataset"] == ds_name:
                        strings[code]["values"].append({
                            "text": str(value) if value is not None else "",
                            "dataset": ds_name,
                            "item_index": item_idx,
                            "field": field_name,
                        })
                        break
    
    total_values = sum(len(s["values"]) for s in strings.values())
    
    result = {
        "generated_at": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "project_id": config["project_id"],
        "total_ids": len(strings),
        "total_values": total_values,
        "by_id": strings,
    }
    
    print(f"[data_analyzer_v2] strings.json: {len(strings)} IDs, {total_values} values", flush=True)
    return result


def _get_libraries(widget: str) -> list:
    """Determine required libraries based on widget type."""
    libs = ["AndroidX"]
    if widget in ("EditText", "TextInputLayout"):
        libs.extend(["Material", "AndroidX"])
    elif widget in ("RecyclerView",):
        libs.extend(["AndroidX", "Material"])
    elif widget in ("ImageView",):
        libs.extend(["Glide", "Picasso"])
    elif widget in ("Switch",):
        libs.extend(["Material"])
    elif widget in ("DatePicker",):
        libs.extend(["Material", "AndroidX"])
    elif widget in ("Spinner",):
        libs.extend(["AndroidX", "Material"])
    elif widget in ("CardView",):
        libs.extend(["AndroidX", "Material"])
    return list(set(libs))


def _get_layout(id_type: str) -> str:
    """Determine layout type based on field type."""
    if id_type in ("Array", "Object"):
        return "grid_layout"
    if id_type in ("Boolean",):
        return "linear_horizontal"
    return "linear_vertical"


def _get_properties(field_name: str, id_type: str, sample: str) -> dict:
    """Generate widget properties based on field name and type."""
    props = {"id": field_name.lower().replace(" ", "_")}
    
    lower_name = field_name.lower()
    if "name" in lower_name:
        props["hint"] = f"Enter {field_name}"
        props["input_type"] = "textPersonName"
    elif "phone" in lower_name or "mobile" in lower_name or "tel" in lower_name:
        props["hint"] = f"Enter {field_name}"
        props["input_type"] = "phone"
    elif "email" in lower_name or "mail" in lower_name:
        props["hint"] = f"Enter {field_name}"
        props["input_type"] = "textEmailAddress"
    elif "date" in lower_name or "admission" in lower_name or "discharge" in lower_name:
        props["hint"] = f"Select {field_name}"
        props["input_type"] = "date"
    elif id_type == "Int":
        props["hint"] = f"Enter {field_name}"
        props["input_type"] = "number"
    elif id_type == "Float":
        props["hint"] = f"Enter {field_name}"
        props["input_type"] = "numberDecimal"
    elif id_type == "Boolean":
        props["text"] = field_name
        props["checked"] = False
    elif id_type == "Enum":
        props["hint"] = f"Select {field_name}"
        props["entries"] = []
    else:
        props["hint"] = f"Enter {field_name}"
        props["input_type"] = "text"
    
    return props


def _get_events(code: str, field_name: str, id_type: str) -> dict:
    """Generate event handlers based on field type."""
    events = {}
    
    lower_name = field_name.lower()
    
    # Text change events
    if id_type in ("String", "Int", "Float", "Email", "Phone"):
        events["onTextChanged"] = f"{code}_validate()"
        if "name" in lower_name:
            events["onSubmit"] = f"{code}_search()"
    
    # Click events
    if id_type in ("Enum",):
        events["onItemSelected"] = f"{code}_on_select()"
    
    # Phone-specific
    if id_type == "Phone":
        events["onClick"] = f"window.location.href='tel:' + {code}"
    
    # URL-specific
    if id_type == "URL":
        events["onClick"] = f"window.open({code})"
    
    # Boolean toggle
    if id_type == "Boolean":
        events["onCheckedChange"] = f"{code}_toggle()"
    
    return events


def _get_oncreate(code: str, field_name: str, id_type: str, dataset: str) -> dict:
    """Generate OnCreate initialization logic."""
    oncreate = {}
    
    # Variables initialization
    if id_type == "String":
        oncreate["Variables"] = f"String {code} = ''"
    elif id_type == "Int":
        oncreate["Variables"] = f"int {code} = 0"
    elif id_type == "Float":
        oncreate["Variables"] = f"double {code} = 0.0"
    elif id_type == "Boolean":
        oncreate["Variables"] = f"bool {code} = false"
    elif id_type == "Array":
        oncreate["Variables"] = f"List {code} = []"
    elif id_type == "Object":
        oncreate["Variables"] = f"Map {code} = {{}}"
    else:
        oncreate["Variables"] = f"var {code} = null"
    
    # Control logic (validation)
    if id_type in ("String", "Email", "Phone"):
        oncreate["Control"] = f"if ({code}.length < 3) showError('Invalid {field_name}')"
    elif id_type == "Int":
        oncreate["Control"] = f"if ({code} < 0) showError('Invalid {field_name}')"
    
    # MoreBlock reference (custom logic)
    oncreate["MoreBlock"] = f"load_from_dataset('{dataset}', '{field_name}')"
    
    return oncreate


# ═══════════════════════════════════════════════════════════════════════════
# 6. MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def analyze_data_files(function_dir: Path, project_name: str = "UniversalApp") -> tuple:
    """Master entry point: analyze all data files and generate config.json + strings.json.
    
    Args:
        function_dir: Path to the function folder (contains media/ subfolder)
        project_name: Optional project name for the config
        
    Returns:
        (config_dict, strings_dict) — also writes them to function_dir/
    """
    global _USED_CODES
    _USED_CODES.clear()  # Reset for each analysis
    
    media_dir = function_dir / "media"
    all_datasets = []
    
    # 1. Parse all files in media/
    if media_dir.exists():
        for file_path in sorted(media_dir.iterdir()):
            if not file_path.is_file() or file_path.name.startswith("_"):
                continue
            
            name = file_path.name
            ext = file_path.suffix.lower()
            
            try:
                content = file_path.read_text(encoding="utf-8")
            except Exception:
                continue
            
            parsed = None
            if ext == ".json":
                try:
                    parsed = parse_json_file(content, name)
                except Exception as e:
                    print(f"[data_analyzer_v2] JSON parse error for {name}: {e}", flush=True)
                    continue
            elif ext == ".csv":
                parsed = parse_csv_file(content, name)
            elif ext == ".txt":
                parsed = parse_txt_file(content, name)
            elif ext in (".html", ".htm"):
                parsed = parse_html_file(content, name)
            else:
                continue
            
            if parsed:
                all_datasets.extend(parsed)
                print(f"[data_analyzer_v2] Parsed {name} ({ext}) -> {len(parsed)} datasets", flush=True)
    
    # 2. Try Excel/PDF/Word via universal parser
    try:
        from engine.excel_parser import parse_any_file
        if media_dir.exists():
            for file_path in sorted(media_dir.iterdir()):
                if not file_path.is_file() or file_path.name.startswith("_"):
                    continue
                ext = file_path.suffix.lower()
                if ext in (".xlsx", ".xls", ".pdf", ".docx"):
                    try:
                        ds = parse_any_file(file_path)
                        if ds:
                            all_datasets.extend(ds)
                            print(f"[data_analyzer_v2] Parsed {name} ({ext}) -> {len(ds)} datasets", flush=True)
                    except Exception as e:
                        print(f"[data_analyzer_v2] Parse error for {file_path.name}: {e}", flush=True)
    except ImportError:
        pass  # excel_parser not available
    
    if not all_datasets:
        print("[data_analyzer_v2] WARNING: No datasets found!", flush=True)
        all_datasets = [{"name": "Empty", "items": []}]
    
    # 3. Build config.json (The Map)
    config = build_config(all_datasets, project_name)
    
    # 4. Build strings.json (The Execution Matrix)
    strings = build_strings(config, all_datasets)
    
    # 5. Write output files
    (function_dir / "config.json").write_text(
        json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (function_dir / "strings.json").write_text(
        json.dumps(strings, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    
    print(f"[data_analyzer_v2] DONE: {config['total_ids']} IDs, {config['total_datasets']} datasets, {config['total_items']} items", flush=True)
    return config, strings


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        if path.exists():
            config, strings = analyze_data_files(path)
            print(f"\n=== config.json sample (first 3 IDs) ===")
            for i, (code, info) in enumerate(config["ids"].items()):
                if i >= 3:
                    break
                print(f"  {code}: {info['original']} ({info['type']}) -> builders: {info['builders']}")
            print(f"\n=== strings.json sample (first ID) ===")
            first_code = list(strings["by_id"].keys())[0]
            print(json.dumps(strings["by_id"][first_code], indent=2))
