"""
build_pipeline.py — Orchestrates all 10 builders + data_analyzer + excel_parser.

This is the master pipeline called by app.py before building the APK.
It runs all builders in order and generates all manifest files.

Order:
  1. excel_parser.py    → parse Excel files (if any)
  2. data_analyzer.py   → config.json + strings.json
  3. variables_builder  → Java variables + strings.xml
  4. view_builder       → layout XMLs
  5. list_builder       → list manifests
  6. control_builder    → tabs + buttons
  7. operator_builder   → click handlers
  8. file_builder       → file access definitions
  9. math_builder       → formula evaluation
 10. component_builder  → reusable components
 11. xml_strings_builder→ final strings.xml
 12. moreblock_builder  → reusable code blocks
"""
import json, os, sys, hashlib, time, base64, traceback
from pathlib import Path

def run_pipeline(function_dir: Path, media_type: str = "hospital") -> dict:
    """Run the full build pipeline on a function directory.
    
    Returns a dict with all manifest data for the template to use.
    """
    results = {"success": True, "errors": []}
    
    # 1. Parse ALL file types (Excel, PDF, Word, JSON, CSV, TXT, HTML) using universal parser
    parsed_datasets = []
    media_dir = function_dir / "media"
    if media_dir.exists():
        for f in sorted(media_dir.iterdir()):
            if not f.is_file():
                continue
            ext = f.suffix.lower()
            # Skip already-merged files
            if f.name.startswith("_"):
                continue
            try:
                from engine.excel_parser import parse_any_file
                ds = parse_any_file(f)
                if ds:
                    parsed_datasets.extend(ds)
                    print(f"[pipeline] Parsed {f.name} ({ext}) → {len(ds)} datasets", flush=True)
            except Exception as e:
                print(f"[pipeline] Parse failed for {f.name}: {e}", flush=True)
                results["errors"].append(f"Parse {f.name}: {e}")
    
    # Merge all parsed datasets into a single JSON for data_analyzer
    if parsed_datasets:
        merged = {"data": {}}
        for ds in parsed_datasets:
            # Clean dataset name for JSON key
            clean_name = ds["name"].replace(" ", "_").replace("-", "_").lower()
            merged["data"][clean_name] = ds["items"]
        (media_dir / "_parsed_merged.json").write_text(
            json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    
    # 2. Run data_analyzer
    try:
        from engine.data_analyzer import analyze_data_files
        config, strings = analyze_data_files(function_dir)
        results["config"] = config
        results["strings"] = strings
    except Exception as e:
        print(f"[pipeline] data_analyzer failed: {e}", flush=True)
        results["errors"].append(f"data_analyzer: {e}")
        # Continue with empty config/strings
        config = {"datasets": [], "fields_index": {}, "codes_index": {}, "total_fields": 0, "total_datasets": 0, "total_items": 0}
        strings = {"by_id": {}, "ordered": [], "summary": {"total_strings": 0, "total_ids": 0}}
        results["config"] = config
        results["strings"] = strings
    
    # 3. variables_builder
    try:
        from engine.variables_builder import build as vb_build
        vb_build(config, strings, function_dir)
    except Exception as e:
        results["errors"].append(f"variables_builder: {e}")
    
    # 4. view_builder
    try:
        from engine.view_builder import build as vwb_build
        vwb_build(config, function_dir)
    except Exception as e:
        results["errors"].append(f"view_builder: {e}")
    
    # 5. list_builder
    try:
        from engine.list_builder import build as lb_build
        lb_build(config, strings, function_dir)
    except Exception as e:
        results["errors"].append(f"list_builder: {e}")
    
    # 6. control_builder
    try:
        from engine.control_builder import build as cb_build
        cb_build(config, function_dir)
    except Exception as e:
        results["errors"].append(f"control_builder: {e}")
    
    # 7. operator_builder
    try:
        from engine.operator_builder import build as ob_build
        ob_build(config, function_dir)
    except Exception as e:
        results["errors"].append(f"operator_builder: {e}")
    
    # 8. file_builder
    try:
        from engine.file_builder import build as fb_build
        fb_build(config, function_dir)
    except Exception as e:
        results["errors"].append(f"file_builder: {e}")
    
    # 9. math_builder
    try:
        from engine.math_builder import build as mb_build
        # Try to load source data for formulas
        source_data = None
        for f in sorted(media_dir.iterdir()) if media_dir.exists() else []:
            if f.suffix.lower() == ".json":
                try:
                    source_data = json.loads(f.read_text(encoding="utf-8"))
                    break
                except: pass
        mb_build(config, strings, function_dir, source_data)
    except Exception as e:
        results["errors"].append(f"math_builder: {e}")
    
    # 10. component_builder
    try:
        from engine.component_builder import build as comp_build
        comp_build(config, function_dir)
    except Exception as e:
        results["errors"].append(f"component_builder: {e}")
    
    # 11. xml_strings_builder
    try:
        from engine.xml_strings_builder import build as xsb_build
        xsb_build(config, strings, function_dir)
    except Exception as e:
        results["errors"].append(f"xml_strings_builder: {e}")
    
    # 12. moreblock_builder
    try:
        from engine.moreblock_builder import build as mbb_build
        mbb_build(config, function_dir)
    except Exception as e:
        results["errors"].append(f"moreblock_builder: {e}")
    
    # Generate unified manifest for the template
    manifest = {
        "config": config,
        "datasets": config.get("datasets", []),
        "total_fields": config.get("total_fields", 0),
        "total_items": config.get("total_items", 0),
        "media_type": media_type,
        "build_errors": results["errors"],
    }
    (function_dir / "_build_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    
    print(f"[pipeline] DONE — {config.get('total_fields',0)} fields, {config.get('total_datasets',0)} datasets, {config.get('total_items',0)} items, {len(results['errors'])} errors", flush=True)
    
    return results


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_pipeline(Path(sys.argv[1]))
