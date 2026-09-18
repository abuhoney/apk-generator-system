#!/usr/bin/env python3
"""
create_render_service.py — Create a NEW Render web service for the backend.

Uses POST /services with the repo + build/start commands from render.yaml.
Does NOT touch existing services.
"""
from __future__ import annotations

import os
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from engine.config import get_config


RENDER_API = "https://api.render.com/v1"


def main() -> int:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--name", default="bardompro-apk-generator")
    p.add_argument("--owner-id", default="tea-d5papfvpm1nc73bsfokg",
                   help="Render owner (team) ID — fetched from GET /owners")
    p.add_argument("--repo", help="GitHub repo URL; defaults to new GitHub repo")
    p.add_argument("--branch", default="main")
    p.add_argument("--plan", default="free")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    cfg = get_config()
    if not cfg.render_api_key:
        print("ERROR: RENDER_API_KEY not set", file=sys.stderr)
        return 1

    repo_url = args.repo or f"https://github.com/{cfg.new_github_repo}"
    body = {
        "type": "web_service",
        "name": args.name,
        "ownerId": args.owner_id,
        "region": "frankfurt",
        "plan": args.plan,
        "branch": args.branch,
        "repo": repo_url,
        "rootDir": ".",
        "runtime": "python",
        "buildCommand": "pip install -r requirements.txt",
        "startCommand": "gunicorn --chdir backend app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120",
        "healthCheckPath": "/api/health",
        "autoDeploy": "yes",
        "envVars": [
            {"key": "PYTHON_VERSION", "value": "3.11.7"},
            {"key": "NODE_ENV", "value": "production"},
        ],
        "serviceDetails": {
            "env": "python",
            "plan": args.plan,
            "region": "frankfurt",
            "runtime": "python",
            "numInstances": 1,
            "healthCheckPath": "/api/health",
            "envSpecificDetails": {
                "env": "python",
                "buildCommand": "pip install -r requirements.txt",
                "startCommand": "gunicorn --chdir backend app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120",
            },
        },
    }

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{RENDER_API}/services",
        data=data, method="POST",
    )
    req.add_header("Authorization", f"Bearer {cfg.render_api_key}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read())
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(f"✓ Created Render service: {result.get('name')}")
                print(f"  id:     {result.get('id')}")
                print(f"  url:    https://{result.get('name')}.onrender.com")
                print(f"  status: {result.get('status')}")
            return 0
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body_text)
        except Exception:
            parsed = {"error": body_text}
        if args.json:
            print(json.dumps(parsed, indent=2))
        else:
            print(f"✗ Failed (HTTP {e.code}): {parsed}")
        return 1
    except Exception as e:
        print(f"✗ Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
