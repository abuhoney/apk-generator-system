"""
function_registry.py — Discovers and registers every function folder.

A "function" is any subdirectory under `functions/` that contains at least
a `handler.py` (Python entry point) OR a `template.html` (web entry point).

Each function is exposed as a `FunctionModule` with:
    - name
    - path
    - manifest (function.json if present, else auto-detected)
    - config.json (built on demand)
    - strings.json (built on demand)
    - template.html (if present)
    - handler.py (if present)
    - assets / css / js subfolders

The registry is the single source of truth for "what functions exist" —
the Flask backend, the CLI, and the Telegram bot all ask it.
"""
from __future__ import annotations

import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from .config import get_config


@dataclass
class FunctionModule:
    name: str
    path: Path
    manifest: dict = field(default_factory=dict)
    has_template: bool = False
    has_handler: bool = False
    has_config_json: bool = False
    has_strings_json: bool = False
    languages: list[str] = field(default_factory=list)
    assets: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": str(self.path),
            "manifest": self.manifest,
            "has_template": self.has_template,
            "has_handler": self.has_handler,
            "has_config_json": self.has_config_json,
            "has_strings_json": self.has_strings_json,
            "languages": self.languages,
            "assets": self.assets,
        }


def _load_manifest(func_dir: Path) -> dict:
    manifest_path = func_dir / "function.json"
    if manifest_path.exists():
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    # Auto-detect a minimal manifest
    return {
        "name": func_dir.name,
        "version": "1.0.0",
        "description": f"Function module: {func_dir.name}",
        "entry": "handler.py" if (func_dir / "handler.py").exists() else "template.html",
    }


def _detect_languages(func_dir: Path) -> list[str]:
    exts = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".java": "java", ".kt": "kotlin", ".html": "html",
        ".css": "css", ".json": "json", ".xml": "xml",
        ".gradle": "gradle", ".sh": "shell", ".md": "markdown",
    }
    found: set[str] = set()
    for p in func_dir.rglob("*"):
        if p.is_file() and not p.name.startswith("."):
            lang = exts.get(p.suffix.lower())
            if lang:
                found.add(lang)
    return sorted(found)


def _list_assets(func_dir: Path) -> list[str]:
    """Return a list of asset subdirectories under the function (css/, js/, assets/)."""
    out: list[str] = []
    for sub in ("css", "js", "assets", "images", "data", "config"):
        if (func_dir / sub).is_dir():
            out.append(sub)
    return out


def discover_function(func_dir: Path) -> Optional[FunctionModule]:
    """Return a FunctionModule if `func_dir` looks like a function folder, else None."""
    if not func_dir.is_dir():
        return None
    # Must have handler.py OR template.html
    has_handler = (func_dir / "handler.py").exists()
    has_template = (func_dir / "template.html").exists()
    if not (has_handler or has_template):
        return None
    return FunctionModule(
        name=func_dir.name,
        path=func_dir,
        manifest=_load_manifest(func_dir),
        has_template=has_template,
        has_handler=has_handler,
        has_config_json=(func_dir / "config.json").exists(),
        has_strings_json=(func_dir / "strings.json").exists(),
        languages=_detect_languages(func_dir),
        assets=_list_assets(func_dir),
    )


class FunctionRegistry:
    """Singleton registry of every available function."""

    def __init__(self, functions_dir: Optional[Path] = None) -> None:
        self.functions_dir = functions_dir or get_config().functions_dir
        self._cache: dict[str, FunctionModule] = {}

    def scan(self) -> dict[str, FunctionModule]:
        if not self.functions_dir.exists():
            return {}
        self._cache = {}
        for child in sorted(self.functions_dir.iterdir()):
            if not child.is_dir():
                continue
            if child.name.startswith(("_", ".")):
                continue
            fm = discover_function(child)
            if fm is not None:
                self._cache[fm.name] = fm
        return self._cache

    def all(self) -> list[FunctionModule]:
        if not self._cache:
            self.scan()
        return list(self._cache.values())

    def get(self, name: str) -> Optional[FunctionModule]:
        if not self._cache:
            self.scan()
        return self._cache.get(name)

    def names(self) -> list[str]:
        if not self._cache:
            self.scan()
        return sorted(self._cache.keys())

    def to_dict(self) -> dict:
        return {"functions": [fm.to_dict() for fm in self.all()]}


_registry: Optional[FunctionRegistry] = None


def get_registry() -> FunctionRegistry:
    global _registry
    if _registry is None:
        _registry = FunctionRegistry()
    return _registry


def reload_registry() -> FunctionRegistry:
    global _registry
    _registry = None
    return get_registry()


if __name__ == "__main__":
    reg = FunctionRegistry()
    for fm in reg.all():
        print(f"  • {fm.name:30s} lang={fm.languages}")
    print(f"\nDiscovered {len(reg.all())} functions.")
