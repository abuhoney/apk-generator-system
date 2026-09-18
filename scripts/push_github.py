#!/usr/bin/env python3
"""
push_github.py — Push the entire project to a NEW GitHub repo.

Creates the repo if it doesn't exist. Never deletes or modifies files
that exist on the remote but not locally — so existing repos are safe.

Usage:
    python3 scripts/push_github.py
    python3 scripts/push_github.py --repo abuhoney/apk-generator-system --dry-run
"""
from __future__ import annotations

import os
import sys
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from engine.config import get_config
from integrations.github_client import GitHubClient


def main() -> int:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--repo", help="Target repo (owner/name). Defaults to NEW_GITHUB_REPO from .env")
    p.add_argument("--branch", default="main")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    cfg = get_config()
    repo = args.repo or cfg.new_github_repo
    token = cfg.github_token

    if not token:
        print("ERROR: GITHUB_TOKEN not set in .env", file=sys.stderr)
        return 1
    if not repo or "/" not in repo:
        print(f"ERROR: invalid repo: {repo!r}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"[DRY RUN] Would push {ROOT} → github.com/{repo} (branch {args.branch})")
        return 0

    gh = GitHubClient(token, repo, args.branch)
    print(f"Pushing {ROOT} → github.com/{repo} (branch {args.branch}) ...")
    t0 = time.time()
    res = gh.push_project(ROOT)
    res.duration_sec = round(time.time() - t0, 1)

    if args.json:
        print(json.dumps(res.to_dict() | {"duration_sec": res.duration_sec}, indent=2))
    else:
        if res.ok:
            print(f"\n✓ Pushed {res.files_pushed} files to {res.repo}")
            if res.files_skipped:
                print(f"  skipped: {res.files_skipped}")
            if res.files_failed:
                print(f"  failed:  {res.files_failed}")
                for err in res.errors:
                    print(f"    {err}")
            print(f"  commit:  {res.commit_url}")
            print(f"  time:    {res.duration_sec}s")
        else:
            print(f"\n✗ Push failed: {res.errors}")
        print()
    return 0 if res.ok else 1


if __name__ == "__main__":
    sys.exit(main())
