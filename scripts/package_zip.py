#!/usr/bin/env python3
"""
package_zip.py — Package the entire project as a downloadable zip.

Excludes build outputs, virtual envs, git metadata, and other clutter.
"""
from __future__ import annotations

import os
import sys
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {"__pycache__", ".git", "node_modules", ".venv", "venv",
             "_builds", "_output", ".idea", ".gradle", "build",
             "self_test_output", "sdk_config"}
# Skip large binary tools (they're downloaded on demand by the builder)
SKIP_LARGE_PATHS = {"android/tools", "android/shell.apk", "android/debug.keystore"}
SKIP_FILES = {".DS_Store", "Thumbs.db"}


def should_skip_dir(name: str) -> bool:
    return name in SKIP_DIRS or name.startswith(".")


def build_zip(project_root: Path, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    total_size = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        top = project_root.name
        for dirpath, dirnames, filenames in os.walk(project_root):
            dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
            for fn in filenames:
                if fn in SKIP_FILES:
                    continue
                full = Path(dirpath) / fn
                # Skip large binary tools (downloaded on demand)
                rel = full.relative_to(project_root)
                rel_posix = rel.as_posix()
                if any(rel_posix.startswith(p) for p in SKIP_LARGE_PATHS):
                    continue
                arc = Path(top) / rel
                zf.write(full, arc.as_posix())
                count += 1
                total_size += full.stat().st_size
    print(f"Packaged {count} files ({total_size / 1024 / 1024:.1f} MB) → {out_path}")
    return out_path


def main() -> int:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(ROOT / "_output" / "apk-generator-system.zip"))
    p.add_argument("--root", default=str(ROOT))
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    out = build_zip(Path(args.root), Path(args.out))
    info = {
        "ok": True,
        "path": str(out),
        "size": out.stat().st_size,
        "size_mb": round(out.stat().st_size / 1024 / 1024, 2),
    }
    if args.json:
        print(json.dumps(info, indent=2))
    else:
        print(f"\n✓ Wrote {info['path']} ({info['size_mb']} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
