"""
file_builder.py — Generates file access definitions for reading data files
from assets/ directory at runtime.
"""
import json
from pathlib import Path

def build(config: dict, function_dir: Path) -> dict:
    media_dir = function_dir / "media"
    files_manifest = {"data_files": [], "config_file": "config.json", "strings_file": "strings.json"}
    
    if media_dir.exists():
        for f in sorted(media_dir.iterdir()):
            if f.is_file():
                ext = f.suffix.lower()
                if ext in (".json", ".csv", ".txt", ".html", ".htm"):
                    files_manifest["data_files"].append({
                        "name": f.name,
                        "path": f"file:///android_asset/webapp/media/{f.name}",
                        "type": ext.lstrip("."),
                        "size": f.stat().st_size,
                    })
    
    (function_dir / "_files_manifest.json").write_text(
        json.dumps(files_manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    
    print(f"[file_builder] {len(files_manifest['data_files'])} data files registered", flush=True)
    return files_manifest
