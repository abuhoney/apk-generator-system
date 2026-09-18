#!/usr/bin/env python3
"""
build_all_metadata.py — Build config.json + strings.json + rendered.html
for every function under functions/.

Usage:
    python3 scripts/build_all_metadata.py
    python3 scripts/build_all_metadata.py --function calculator
"""
from __future__ import annotations

import os
import sys
import json
from pathlib import Path

# Make sure the backend is importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from engine.config import get_config
from engine.config_json_processor import write_config_json, build_config_json
from engine.strings_json_processor import write_strings_json, build_strings_json
from engine.template_renderer import render_to_file
from engine.function_registry import get_registry, reload_registry


def main() -> int:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--function", help="Only build this function (default: all)")
    p.add_argument("--json", action="store_true", help="Output JSON")
    args = p.parse_args()

    reg = reload_registry()
    results = []
    for fm in reg.all():
        if args.function and fm.name != args.function:
            continue
        cfg_path = write_config_json(fm.path, fm.name)
        str_path = write_strings_json(fm.path, fm.name)
        tpl_path = None
        if fm.has_template:
            try:
                tpl_path = render_to_file(fm.path)
            except Exception as e:
                print(f"  ⚠ template render failed for {fm.name}: {e}")
        results.append({
            "function": fm.name,
            "config_json": str(cfg_path),
            "strings_json": str(str_path),
            "rendered_html": str(tpl_path) if tpl_path else None,
        })

    if args.json:
        print(json.dumps({"ok": True, "results": results, "count": len(results)}, indent=2))
    else:
        for r in results:
            print(f"  ✓ {r['function']:20s} config.json + strings.json" +
                  (f" + rendered.html" if r["rendered_html"] else ""))
        print(f"\nBuilt metadata for {len(results)} function(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
