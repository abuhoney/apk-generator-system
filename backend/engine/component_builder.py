"""
component_builder.py — Generates reusable UI component definitions
from config.json field patterns.

Identifies repeated field patterns across datasets and creates
reusable component templates (e.g., "doctor_card", "patient_card").
"""
import json, re
from pathlib import Path

def build(config: dict, function_dir: Path) -> dict:
    datasets = config.get("datasets", [])
    components = {"cards": [], "badges": [], "stats": []}
    
    # Detect card components (one per dataset)
    icons = {"patients":"\U0001f465","doctors":"\U0001fa7a","nurses":"\U0001f489","appointments":"\U0001f4c5",
             "rooms":"\U0001f6cf\ufe0f","medicines":"\U0001f48a","invoices":"\U0001f4b0","emergency":"\U0001f6a8",
             "products":"\U0001f4e6","contacts":"\U0001f4de","services":"\U0001f527"}
    
    for ds in datasets:
        name = ds.get("name", "data")
        fields = ds.get("fields", [])
        icon = icons.get(name.lower(), "\U0001f4cb")
        
        # Determine primary fields for the card
        title_field = None
        subtitle_fields = []
        for f in fields:
            if f["field"] in ("name", "title", "patient", "doctor", "product", "item") and not title_field:
                title_field = f["field"]
            elif f["field"] not in ("id", "patient_id", "appt_id", "case_id", "invoice_id", "code") and len(subtitle_fields) < 3:
                subtitle_fields.append(f["field"])
        
        components["cards"].append({
            "name": f"{name.lower()}_card",
            "dataset": name,
            "icon": icon,
            "title_field": title_field or fields[0]["field"] if fields else "name",
            "subtitle_fields": subtitle_fields,
            "total_fields": len(fields),
            "item_count": ds.get("item_count", 0),
        })
    
    # Detect status/type badge fields
    for ds in datasets:
        for f in ds.get("fields", []):
            if f["field"] in ("status", "severity", "type", "category", "gender", "shift"):
                components["badges"].append({
                    "field": f["field"],
                    "dataset": ds["name"],
                    "type": f.get("type", "str"),
                })
    
    # Generate stats from dataset counts
    for ds in datasets:
        components["stats"].append({
            "label": ds["name"],
            "value": ds.get("item_count", 0),
            "icon": icons.get(ds["name"].lower(), "\U0001f4cb"),
        })
    
    (function_dir / "_components_manifest.json").write_text(
        json.dumps(components, indent=2, ensure_ascii=False), encoding="utf-8")
    
    print(f"[component_builder] {len(components['cards'])} cards, {len(components['badges'])} badges, {len(components['stats'])} stats", flush=True)
    return components
