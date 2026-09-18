#!/usr/bin/env python3
"""
deploy_render.py — Trigger a Render deploy for the backend service.

Usage:
    python3 scripts/deploy_render.py
    python3 scripts/deploy_render.py --status
"""
from __future__ import annotations

import os
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from engine.config import get_config
from integrations.render_client import RenderClient


def main() -> int:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--status", action="store_true", help="Only print service status")
    p.add_argument("--suspend", action="store_true")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    cfg = get_config()
    if not cfg.render_api_key or not cfg.render_service_id:
        print("ERROR: RENDER_API_KEY / RENDER_SERVICE_ID not set in .env", file=sys.stderr)
        return 1

    rc = RenderClient(cfg.render_api_key, cfg.render_service_id)

    if args.status:
        data = rc.health()
    elif args.suspend:
        data = rc.suspend()
    elif args.resume:
        data = rc.resume()
    else:
        data = rc.deploy()

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        if data.get("ok") or data.get("status"):
            print("✓", json.dumps(data, indent=2))
        else:
            print("✗", json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
