"""
zip_builder.py — Packages the entire project as a downloadable zip.

Excludes build outputs, virtual envs, git metadata, and other clutter
so the resulting zip is small and clean.
"""
from __future__ import annotations

import os
import zipfile
from pathlib import Path


SKIP_DIRS = {"__pycache__", ".git", "node_modules", ".venv", "venv",
             "_builds", "_output", ".idea", ".gradle", "build",
             "self_test_output", "sdk_config"}
SKIP_FILES = {".DS_Store", "Thumbs.db"}


def _should_skip_dir(name: str) -> bool:
    return name in SKIP_DIRS or name.startswith(".")


def build_project_zip(project_root: Path, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        # Top-level dir in the zip is the project name
        top = project_root.name
        for dirpath, dirnames, filenames in os.walk(project_root):
            dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]
            for fn in filenames:
                if fn in SKIP_FILES:
                    continue
                full = Path(dirpath) / fn
                arc = Path(top) / full.relative_to(project_root)
                zf.write(full, arc.as_posix())
    return out_path


def build_function_zip(function_dir: Path, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        top = function_dir.name
        for dirpath, dirnames, filenames in os.walk(function_dir):
            dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]
            for fn in filenames:
                if fn in SKIP_FILES:
                    continue
                full = Path(dirpath) / fn
                arc = Path(top) / full.relative_to(function_dir)
                zf.write(full, arc.as_posix())
    return out_path


if __name__ == "__main__":
    import sys
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("project.zip")
    p = build_project_zip(root, out)
    print(f"Wrote {p} ({p.stat().st_size} bytes)")
