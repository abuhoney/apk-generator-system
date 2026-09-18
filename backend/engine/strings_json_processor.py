"""
strings_json_processor.py — Builds strings.json for a single function folder.

strings.json contains, for every ID, every string that appears inside that
ID's code block — in the exact order they appear in the source file, from
file start to file end, no truncation, no redaction. Branching is preserved:
sub-functions contribute their strings under their parent's entry as well as
their own.

Output schema (strings.json):

{
  "function": "calculator",
  "version": "1.0.0",
  "generated_at": "2026-09-18T...Z",
  "summary": {
    "files": 7,
    "total_strings": 87,
    "ids_with_strings": 12
  },
  "global_strings": [                 # strings not inside any ID
    {"text": "Calculator", "file": "handler.py", "line": 1}
  ],
  "by_id": {
    "calculate_total": [
      {"text": "Total amount", "file": "handler.py", "line": 14},
      {"text": "Invalid input", "file": "handler.py", "line": 18},
      ...
    ],
    "_validate_input": [
      {"text": "Please enter a number", "file": "handler.py", "line": 25},
      ...
    ],
    ...
  },
  "ordered": [                        # every string in file→line order
    {"text": "Calculator", "file": "handler.py", "line": 1, "id": null},
    {"text": "Total amount", "file": "handler.py", "line": 14, "id": "calculate_total"},
    ...
  ]
}
"""
from __future__ import annotations

import json
import datetime
from pathlib import Path
from collections import defaultdict
from dataclasses import asdict
from typing import Optional

from .code_extractor import extract_folder, FileExtraction, StringEntry


def _summarize(extractions: list[FileExtraction]) -> dict:
    total = sum(len(fe.strings) for fe in extractions)
    ids_with_strings = len({
        s.id_at_line for fe in extractions for s in fe.strings if s.id_at_line
    })
    return {
        "files": len(extractions),
        "total_strings": total,
        "ids_with_strings": ids_with_strings,
    }


def _by_id(extractions: list[FileExtraction]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for fe in extractions:
        for s in fe.strings:
            if s.id_at_line:
                out[s.id_at_line].append({
                    "text": s.text,
                    "file": fe.path,
                    "line": s.line,
                })
    # Sort each list by file then line so order matches source
    for k, v in out.items():
        v.sort(key=lambda x: (x["file"], x["line"]))
    return dict(out)


def _global_strings(extractions: list[FileExtraction]) -> list[dict]:
    out: list[dict] = []
    for fe in extractions:
        for s in fe.strings:
            if not s.id_at_line:
                out.append({
                    "text": s.text,
                    "file": fe.path,
                    "line": s.line,
                })
    out.sort(key=lambda x: (x["file"], x["line"]))
    return out


def _ordered(extractions: list[FileExtraction]) -> list[dict]:
    """Every string in file→line order, with its enclosing ID (or null)."""
    out: list[dict] = []
    for fe in extractions:
        for s in fe.strings:
            out.append({
                "text": s.text,
                "file": fe.path,
                "line": s.line,
                "id": s.id_at_line,
            })
    out.sort(key=lambda x: (x["file"], x["line"]))
    return out


def build_strings_json(function_dir: Path,
                       function_name: Optional[str] = None,
                       version: str = "1.0.0") -> dict:
    """Walk `function_dir`, extract every string per ID in order, and return
    the strings.json structure as a dict."""
    if function_name is None:
        function_name = function_dir.name

    extractions = extract_folder(function_dir)

    return {
        "function": function_name,
        "version": version,
        "generated_at": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "summary": _summarize(extractions),
        "global_strings": _global_strings(extractions),
        "by_id": _by_id(extractions),
        "ordered": _ordered(extractions),
    }


def write_strings_json(function_dir: Path,
                       function_name: Optional[str] = None,
                       version: str = "1.0.0") -> Path:
    data = build_strings_json(function_dir, function_name, version)
    out = function_dir / "strings.json"
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def build_all(functions_root: Path) -> dict[str, Path]:
    written: dict[str, Path] = {}
    for child in sorted(functions_root.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith("_") or child.name.startswith("."):
            continue
        path = write_strings_json(child, child.name)
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
    print(f"\nWrote strings.json for {len(written)} functions.")
