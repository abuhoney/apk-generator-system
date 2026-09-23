"""
control_builder.py — Generates UI control definitions (tabs, buttons, toggles)
from config.json datasets.
"""
import json
from pathlib import Path

def build(config: dict, function_dir: Path) -> dict:
    datasets = config.get("datasets", [])
    controls = {"tabs": [], "buttons": [], "search_enabled": True}
    
    icons = {"patients":"\U0001f465","doctors":"\U0001fa7a","nurses":"\U0001f489","appointments":"\U0001f4c5",
             "rooms":"\U0001f6cf\ufe0f","medicines":"\U0001f48a","invoices":"\U0001f4b0","emergency":"\U0001f6a8",
             "products":"\U0001f4e6","items":"\U0001f4cb","contacts":"\U0001f4de","services":"\U0001f527",
             "staff":"\U0001f468\u200d\u2695\ufe0f","_meta":"\u2139\ufe0f","beds_stats":"\U0001f6cf\ufe0f",
             "revenue_monthly":"\U0001f4ca","operations_stats":"\U0001f4ca","data":"\U0001f4c4"}
    
    for ds in datasets:
        name = ds.get("name", "data")
        icon = icons.get(name.lower(), "\U0001f4cb")
        controls["tabs"].append({
            "label": name,
            "icon": icon,
            "dataset": name,
            "item_count": ds.get("item_count", 0),
        })
    
    # Add search control if more than 1 dataset
    controls["search_enabled"] = len(datasets) > 1
    
    # Write controls manifest
    (function_dir / "_controls_manifest.json").write_text(
        json.dumps(controls, indent=2, ensure_ascii=False), encoding="utf-8")
    
    print(f"[control_builder] {len(controls['tabs'])} tabs, search={'on' if controls['search_enabled'] else 'off'}", flush=True)
    return controls
