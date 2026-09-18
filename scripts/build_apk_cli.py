#!/usr/bin/env python3
"""
build_apk_cli.py — Build an APK for a single function via the CLI.

Usage:
    python3 scripts/build_apk_cli.py calculator
    python3 scripts/build_apk_cli.py calculator --app-name "My Calc" --version-name 1.0.0
"""
from __future__ import annotations

import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from engine.config_json_processor import write_config_json
from engine.strings_json_processor import write_strings_json
from engine.template_renderer import render_to_file
from engine.function_registry import get_registry, reload_registry

# Prefer v2 builder (real installable APKs)
try:
    from engine.apk_builder_v2 import build_apk
    _BUILDER = "v2"
except Exception as e:
    from engine.apk_builder import build_apk
    _BUILDER = "v1"
    print(f"⚠ v2 builder unavailable ({e}); falling back to v1 webapk", file=sys.stderr)


def main() -> int:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("function", help="Function name (e.g. calculator)")
    p.add_argument("--app-name", help="App display name")
    p.add_argument("--package", help="Android package name")
    p.add_argument("--version-name", default="1.0.0")
    p.add_argument("--version-code", type=int, default=1)
    p.add_argument("--force-webapk", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    reg = reload_registry()
    fm = reg.get(args.function)
    if fm is None:
        print(f"ERROR: function not found: {args.function}", file=sys.stderr)
        print(f"Available: {', '.join(reg.names())}", file=sys.stderr)
        return 1

    # Build metadata first so the APK ships with fresh config.json/strings.json
    write_config_json(fm.path, fm.name)
    write_strings_json(fm.path, fm.name)
    if fm.has_template:
        render_to_file(fm.path)

    res = build_apk(
        args.function,
        app_name=args.app_name,
        package_name=args.package,
        version_code=args.version_code,
        version_name=args.version_name,
        force_webapk=args.force_webapk,
    )

    if args.json:
        print(json.dumps(res.to_dict(), indent=2))
    else:
        if res.success:
            print(f"\n✓ Built {res.function} → {res.apk_path}")
            print(f"  mode:  {res.build_mode}")
            print(f"  size:  {res.apk_size / 1024:.1f} KB")
            print(f"  time:  {res.duration_sec:.1f}s")
        else:
            print(f"\n✗ Build failed: {res.error}")
    return 0 if res.success else 1


if __name__ == "__main__":
    sys.exit(main())
