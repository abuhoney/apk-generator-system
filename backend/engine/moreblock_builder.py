"""
moreblock_builder.py — Generates reusable code blocks (more blocks) that can
be embedded into any template or generated Java code.

These are logical units like:
- "load_dataset_block" — loads a dataset from assets
- "render_list_block" — renders a list with cards
- "search_block" — filters items by query
- "detail_view_block" — shows item details
"""
import json
from pathlib import Path

def build(config: dict, function_dir: Path) -> dict:
    datasets = config.get("datasets", [])
    blocks = {"blocks": []}
    
    # Block: Load each dataset
    for ds in datasets:
        name = ds["name"]
        blocks["blocks"].append({
            "name": f"load_{name}",
            "type": "data_load",
            "dataset": name,
            "description": f"Load {name} dataset from assets",
        })
    
    # Block: Render list for each dataset
    for ds in datasets:
        name = ds["name"]
        blocks["blocks"].append({
            "name": f"render_{name}_list",
            "type": "render_list",
            "dataset": name,
            "fields": [f["field"] for f in ds.get("fields", [])[:5]],
            "description": f"Render {name} as a list with cards",
        })
    
    # Block: Search
    blocks["blocks"].append({
        "name": "search_all",
        "type": "search",
        "description": "Search across all datasets",
    })
    
    # Block: Detail view
    blocks["blocks"].append({
        "name": "show_detail",
        "type": "detail_view",
        "description": "Show item details in a modal/viewer",
    })
    
    # Block: Share via WhatsApp
    blocks["blocks"].append({
        "name": "share_whatsapp",
        "type": "action",
        "description": "Share app via WhatsApp",
    })
    
    # Block: Rate app
    blocks["blocks"].append({
        "name": "rate_app",
        "type": "action",
        "description": "Rate the app",
    })
    
    (function_dir / "_moreblocks_manifest.json").write_text(
        json.dumps(blocks, indent=2, ensure_ascii=False), encoding="utf-8")
    
    print(f"[moreblock_builder] {len(blocks['blocks'])} code blocks", flush=True)
    return blocks
