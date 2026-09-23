"""
list_builder.py — Generates RecyclerView adapter logic (as HTML/JS template data)
from config.json datasets.

Produces a JSON manifest that the HTML template uses to render lists.
"""
import json
from pathlib import Path

def build(config: dict, strings: dict, function_dir: Path) -> dict:
    datasets = config.get("datasets", [])
    lists_manifest = []
    
    for ds in datasets:
        ds_name = ds.get("name", "data")
        fields = ds.get("fields", [])
        item_count = ds.get("item_count", 0)
        
        # Determine list grouping field
        group_field = None
        for f in fields:
            if f["field"] in ("department", "dept", "specialty", "category", "type", "status", "gender", "floor", "severity", "brand"):
                group_field = f["field"]
                break
        
        # Determine display name field
        name_field = None
        for f in fields:
            if f["field"] in ("name", "patient", "doctor", "title", "product", "medicine_name", "item"):
                name_field = f["field"]
                break
        if not name_field and fields:
            name_field = fields[0]["field"]
        
        lists_manifest.append({
            "dataset": ds_name,
            "item_count": item_count,
            "fields": [f["field"] for f in fields],
            "name_field": name_field,
            "group_field": group_field,
            "display_fields": [f["field"] for f in fields[:5]],  # max 5 display fields
        })
    
    # Write manifest
    (function_dir / "_lists_manifest.json").write_text(
        json.dumps(lists_manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    
    print(f"[list_builder] {len(lists_manifest)} list manifests", flush=True)
    return {"lists": len(lists_manifest), "manifest": lists_manifest}
