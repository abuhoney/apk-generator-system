"""
config_json_processor.py — Builds config.json for a single function folder.

config.json contains, for every ID in the function folder, the FULL code
block from start to end — no truncation, no redaction — while preserving
the branching structure (sub-functions point to their parent).

Output schema (config.json):

{
  "function": "calculator",
  "version": "1.0.0",
  "generated_at": "2026-09-18T...Z",
  "summary": {
    "files": 7,
    "ids": 42,
    "languages": ["python", "html", "css", "javascript"]
  },
  "files": [
    {
      "path": "handler.py",
      "language": "python",
      "lines": 142,
      "ids": [
        {
          "id": "calculate_total",
          "kind": "function",
          "line_start": 12,
          "line_end": 28,
          "code": "def calculate_total(...):\n    ...",
          "branch_of": null,
          "children": ["_validate_input", "_format_output"]
        },
        ...
      ]
    },
    ...
  ],
  "ids_index": {
    "calculate_total": {"file": "handler.py", "line_start": 12, "line_end": 28, "kind": "function"},
    ...
  },
  "tree": {
    "calculate_total": {
      "_meta": {"kind": "function", "file": "handler.py", "line_start": 12, "line_end": 28},
      "_code": "def calculate_total(...):\n    ...",
      "children": {
        "_validate_input": {
          "_meta": {...}, "_code": "def _validate_input(...):\n    ...", "children": {}
        },
        ...
      }
    },
    ...
  }
}
"""
from __future__ import annotations

import json
import datetime
from pathlib import Path
from dataclasses import asdict
from typing import Optional

from .code_extractor import extract_folder, FileExtraction, IdEntry


def _build_ids_index(extractions: list[FileExtraction]) -> dict:
    """Lightweight index — no code, just metadata for fast lookup."""
    idx: dict[str, dict] = {}
    for fe in extractions:
        for entry in fe.ids:
            key = f"{fe.path}::{entry.id}" if entry.id in idx else entry.id
            idx[key] = {
                "file": fe.path,
                "line_start": entry.line_start,
                "line_end": entry.line_end,
                "kind": entry.kind,
                "branch_of": entry.branch_of,
            }
    return idx


def _build_tree(extractions: list[FileExtraction]) -> dict:
    """Build a parent → children tree of every ID, with code referenced
    by index instead of duplicated inline. Each node stores `_code_ref`
    which is a key into `ids_index` (file::id) — keeps the JSON small."""
    flat: dict[str, dict] = {}
    for fe in extractions:
        for entry in fe.ids:
            key = entry.id
            # If duplicate ID across files, qualify by file
            if key in flat and flat[key]["_meta"]["file"] != fe.path:
                key = f"{fe.path}::{entry.id}"
            flat[key] = {
                "_meta": {
                    "kind": entry.kind,
                    "file": fe.path,
                    "line_start": entry.line_start,
                    "line_end": entry.line_end,
                    "branch_of": entry.branch_of,
                },
                "_code_ref": key,
                "children": {},
            }

    # Now wire parent → child
    roots: dict[str, dict] = {}
    for key, node in flat.items():
        parent_id = node["_meta"]["branch_of"]
        if parent_id and parent_id in flat:
            flat[parent_id]["children"][key] = node
        else:
            roots[key] = node
    return roots


def _summarize(extractions: list[FileExtraction]) -> dict:
    files = len(extractions)
    ids = sum(len(fe.ids) for fe in extractions)
    langs = sorted({fe.language for fe in extractions})
    return {"files": files, "ids": ids, "languages": langs}


def build_config_json(function_dir: Path,
                      function_name: Optional[str] = None,
                      version: str = "1.0.0") -> dict:
    """Walk `function_dir`, extract every ID with its full code, and return
    the config.json structure as a dict."""
    if function_name is None:
        function_name = function_dir.name

    extractions = extract_folder(function_dir)

    return {
        "function": function_name,
        "version": version,
        "generated_at": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "summary": _summarize(extractions),
        "files": [
            {
                "path": fe.path,
                "language": fe.language,
                "lines": fe.lines,
                "ids": [asdict(i) for i in fe.ids],
            }
            for fe in extractions
        ],
        "ids_index": _build_ids_index(extractions),
        "tree": _build_tree(extractions),
    }


def write_config_json(function_dir: Path,
                      function_name: Optional[str] = None,
                      version: str = "1.0.0") -> Path:
    """Build config.json for the function and write it into the function dir."""
    data = build_config_json(function_dir, function_name, version)
    out = function_dir / "config.json"
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def build_all(functions_root: Path) -> dict[str, Path]:
    """Build config.json for every function folder under `functions_root`."""
    written: dict[str, Path] = {}
    for child in sorted(functions_root.iterdir()):
        if not child.is_dir():
            continue
        # Skip non-function dirs
        if child.name.startswith("_") or child.name.startswith("."):
            continue
        path = write_config_json(child, child.name)
        written[child.name] = path
    return written


if __name__ == "__main__":
    import sys
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("functions")
    if not target.exists():
        print(f"Target not found: {target}")
        sys.exit(1)
    written = build_all(target)
    for name, path in written.items():
        print(f"  ✓ {name:30s} → {path}")
    print(f"\nWrote config.json for {len(written)} functions.")
