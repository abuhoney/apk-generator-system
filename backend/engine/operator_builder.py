"""
operator_builder.py — Generates event handler definitions for click actions
on list items, buttons, and navigation.
"""
import json
from pathlib import Path

def build(config: dict, function_dir: Path) -> dict:
    datasets = config.get("datasets", [])
    events = {"click_handlers": [], "navigation": []}
    
    for ds in datasets:
        name = ds.get("name", "data")
        fields = ds.get("fields", [])
        
        # Click handler for each item → opens detail view
        events["click_handlers"].append({
            "target": f"item_{name}",
            "action": "open_detail",
            "dataset": name,
            "fields_to_show": [f["field"] for f in fields[:10]],
        })
        
        # If there's a phone field, add call action
        for f in fields:
            if f["field"] in ("phone", "tel", "mobile", "contact"):
                events["click_handlers"].append({
                    "target": f"item_{name}_phone",
                    "action": "dial",
                    "field": f["field"],
                })
                break
    
    # Write events manifest
    (function_dir / "_events_manifest.json").write_text(
        json.dumps(events, indent=2, ensure_ascii=False), encoding="utf-8")
    
    print(f"[operator_builder] {len(events['click_handlers'])} click handlers", flush=True)
    return events
