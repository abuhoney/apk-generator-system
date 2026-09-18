#!/usr/bin/env python3
"""
list_functions.py — List every available function module.
"""
from __future__ import annotations

import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from engine.function_registry import reload_registry


def main() -> int:
    reg = reload_registry()
    if "--json" in sys.argv:
        print(json.dumps(reg.to_dict(), indent=2))
        return 0
    fns = reg.all()
    if not fns:
        print("No functions discovered. Add a function folder under functions/")
        return 0
    print(f"Discovered {len(fns)} function(s):\n")
    for fm in fns:
        print(f"  • {fm.name:20s} lang={','.join(fm.languages)}")
        print(f"    {'  has:':20s} " +
              " ".join([x for x in ["handler.py" if fm.has_handler else "",
                                    "template.html" if fm.has_template else "",
                                    "config.json" if fm.has_config_json else "",
                                    "strings.json" if fm.has_strings_json else ""] if x]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
