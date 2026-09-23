"""
data_analyzer.py — Analyzes uploaded JSON/CSV data files and generates
config.json + strings.json with unique 5-char ID codes for every field.

Usage:
    from engine.data_analyzer import analyze_data_files
    config, strings = analyze_data_files(function_dir)
"""
from __future__ import annotations

import json
import hashlib
import datetime
from pathlib import Path
from typing import Any


def _generate_code(field_name: str, index: int) -> str:
    """Generate a unique 5-character code from field name + index."""
    h = hashlib.md5(f"{field_name}_{index}".encode()).digest()
    chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    code = ""
    for b in h[:5]:
        code += chars[b % len(chars)]
    return code


def _extract_fields(item: dict, prefix: str = "") -> list:
    """Extract all fields from a data item (flattens nested)."""
    fields = []
    for key, value in item.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            fields.extend(_extract_fields(value, full_key))
        elif isinstance(value, list):
            fields.append({"field": full_key, "type": "array", "sample": value[:3] if value else []})
        else:
            fields.append({"field": full_key, "type": type(value).__name__, "sample": value})
    return fields


def _detect_datasets(data: Any, file_name: str) -> list:
    """Detect datasets in parsed JSON data."""
    import re as _re
    datasets = []
    if isinstance(data, list):
        name = _re.sub(r'\.[^.]+$', '', file_name).replace('_', ' ').title() if file_name else "Data"
        datasets.append({"name": name, "items": data})
        return datasets
    if not isinstance(data, dict):
        return datasets
    # Check for "data" wrapper
    if "data" in data and isinstance(data["data"], dict):
        for key, val in data["data"].items():
            if isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict):
                datasets.append({"name": key, "items": val})
        if datasets:
            meta = {k: v for k, v in data.items() if k != "data" and not isinstance(v, (list, dict))}
            if meta:
                datasets.insert(0, {"name": "_meta", "items": [meta]})
            return datasets
    # Direct array values
    for key, val in data.items():
        if isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict):
            datasets.append({"name": key, "items": val})
    if datasets:
        return datasets
    # Single object
    name = _re.sub(r'\.[^.]+$', '', file_name).replace('_', ' ').title() if file_name else "Data"
    datasets.append({"name": name, "items": [data]})
    return datasets


def _parse_csv(text: str) -> list:
    """Parse CSV into list of dicts."""
    lines = text.strip().split("\n")
    if len(lines) < 2:
        return []
    headers = [h.strip() for h in lines[0].split(",")]
    items = []
    for line in lines[1:]:
        vals = line.split(",")
        item = {}
        for i, h in enumerate(headers):
            v = vals[i].strip() if i < len(vals) else ""
            try: v = int(v)
            except ValueError:
                try: v = float(v)
                except ValueError: pass
            item[h] = v
        items.append(item)
    return items


def analyze_data_files(function_dir: Path) -> tuple:
    """Analyze data files in function_dir/media/ and generate config.json + strings.json."""
    media_dir = function_dir / "media"
    all_datasets = []
    all_fields = {}  # field_name → {code, type, datasets}
    field_index = 0

    if media_dir.exists():
        for file_path in sorted(media_dir.iterdir()):
            if not file_path.is_file():
                continue
            name = file_path.name
            ext = file_path.suffix.lower()
            try:
                content = file_path.read_text(encoding="utf-8")
            except: continue

            parsed = None
            if ext == ".json":
                try: parsed = json.loads(content)
                except: continue
            elif ext == ".csv":
                parsed = _parse_csv(content)
            elif ext == ".txt":
                items = []
                for line in content.strip().split("\n"):
                    line = line.strip()
                    if not line: continue
                    if ":" in line:
                        k, v = line.split(":", 1)
                        items.append({"name": k.strip(), "value": v.strip()})
                    else:
                        items.append({"name": line})
                parsed = items
            else:
                continue
            if parsed is None: continue

            datasets = _detect_datasets(parsed, name)
            for ds in datasets:
                ds_fields = []
                if ds["items"] and isinstance(ds["items"][0], dict):
                    seen = set()
                    for item in ds["items"]:
                        for f in _extract_fields(item):
                            if f["field"] not in seen:
                                seen.add(f["field"])
                                ds_fields.append(f)
                                if f["field"] not in all_fields:
                                    code = _generate_code(f["field"], field_index)
                                    field_index += 1
                                    all_fields[f["field"]] = {"code": code, "type": f["type"], "sample": f["sample"], "datasets": []}
                                all_fields[f["field"]]["datasets"].append(ds["name"])
                ds["fields"] = ds_fields
                all_datasets.append(ds)

    config = {
        "generated_at": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "total_datasets": len(all_datasets),
        "total_fields": len(all_fields),
        "total_items": sum(len(ds["items"]) for ds in all_datasets),
        "datasets": [
            {"name": ds["name"], "item_count": len(ds["items"]),
             "fields": [{"field": f["field"], "code": all_fields.get(f["field"], {}).get("code", "?????"), "type": f["type"]}
                        for f in ds.get("fields", [])]}
            for ds in all_datasets
        ],
        "fields_index": {name: {"code": info["code"], "type": info["type"], "datasets": info["datasets"]}
                         for name, info in all_fields.items()},
        "codes_index": {info["code"]: name for name, info in all_fields.items()},
    }

    strings = {"generated_at": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
               "total_datasets": len(all_datasets), "by_id": {}, "ordered": []}
    for ds in all_datasets:
        for item_idx, item in enumerate(ds["items"]):
            if not isinstance(item, dict): continue
            for field_name, value in item.items():
                if field_name not in all_fields: continue
                code = all_fields[field_name]["code"]
                str_value = str(value) if value is not None else ""
                if code not in strings["by_id"]:
                    strings["by_id"][code] = []
                entry = {"text": str_value, "dataset": ds["name"], "item_index": item_idx, "field": field_name}
                strings["by_id"][code].append(entry)
                strings["ordered"].append(entry)
    strings["summary"] = {"total_strings": len(strings["ordered"]), "total_ids": len(strings["by_id"])}

    (function_dir / "config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    (function_dir / "strings.json").write_text(json.dumps(strings, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[data_analyzer] config: {len(all_fields)} fields, {len(all_datasets)} datasets | strings: {len(strings['ordered'])} entries, {len(strings['by_id'])} IDs", flush=True)
    return config, strings


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        analyze_data_files(Path(sys.argv[1]))
