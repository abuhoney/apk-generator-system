"""
github_client.py — Pushes the project to a NEW GitHub repo.

The client uses the GitHub REST API directly (no third-party dependency)
to:
    1. Check if the target repo exists; if not, create it.
    2. Walk the local project tree and upsert every file via the
       "create or update file contents" endpoint.
    3. Never delete or modify files that exist on the remote but not
       locally — so existing repos are never damaged.

Each upsert is a single API call. Binary files are base64-encoded.

Usage:
    gh = GitHubClient(token, "abuhoney/apk-generator-system")
    gh.push_project(Path("/path/to/project"))
"""
from __future__ import annotations

import os
import base64
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


GITHUB_API = "https://api.github.com"

SKIP_DIRS = {"__pycache__", ".git", "node_modules", ".venv", "venv",
             "_builds", "_output", ".idea", ".gradle", "build",
             "self_test_output", "sdk_config"}
SKIP_FILES = {".DS_Store", "Thumbs.db"}
MAX_FILE_SIZE = 50 * 1024 * 1024   # GitHub's per-file limit


@dataclass
class PushResult:
    ok: bool
    repo: str
    branch: str
    files_pushed: int
    files_skipped: int
    files_failed: int
    errors: list[str]
    commit_url: Optional[str] = None

    def to_dict(self) -> dict:
        return self.__dict__


class GitHubClient:
    def __init__(self, token: str, repo: str, branch: str = "main") -> None:
        self.token = token
        self.repo = repo                  # e.g. "abuhoney/apk-generator-system"
        self.branch = branch
        self._headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    # ------------------------------------------------------------------ #
    # Low-level HTTP helpers
    # ------------------------------------------------------------------ #
    def _request(self, method: str, path: str,
                 body: Optional[dict] = None,
                 content_type: str = "application/json") -> tuple[int, dict]:
        url = f"{GITHUB_API}{path}"
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method=method)
        for k, v in self._headers.items():
            req.add_header(k, v)
        req.add_header("Content-Type", content_type)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.loads(r.read() or "{}")
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(body_text)
            except Exception:
                parsed = {"error": body_text}
            return e.code, parsed
        except Exception as e:
            return 0, {"error": str(e)}

    # ------------------------------------------------------------------ #
    # Repo management
    # ------------------------------------------------------------------ #
    def repo_exists(self) -> bool:
        code, _ = self._request("GET", f"/repos/{self.repo}")
        return code == 200

    def create_repo(self, private: bool = True, description: str = "") -> bool:
        # Extract owner from repo string
        owner = self.repo.split("/")[0]
        body = {
            "name": self.repo.split("/")[-1],
            "private": private,
            "description": description or "BardomPro APK Generator",
            "auto_init": True,
        }
        code, _ = self._request("POST", f"/user/repos", body)
        return code == 201

    def ensure_repo(self, private: bool = True, description: str = "") -> bool:
        if self.repo_exists():
            return True
        return self.create_repo(private=private, description=description)

    # ------------------------------------------------------------------ #
    # File upsert
    # ------------------------------------------------------------------ #
    def get_file_sha(self, path_in_repo: str) -> Optional[str]:
        code, data = self._request(
            "GET",
            f"/repos/{self.repo}/contents/{path_in_repo}?ref={self.branch}",
        )
        if code == 200 and isinstance(data, dict):
            return data.get("sha")
        return None

    def upsert_file(self, local_path: Path, path_in_repo: str) -> tuple[bool, str]:
        if local_path.stat().st_size > MAX_FILE_SIZE:
            return False, "file too large (>50MB)"
        raw = local_path.read_bytes()
        b64 = base64.b64encode(raw).decode("ascii")
        sha = self.get_file_sha(path_in_repo)
        body = {
            "message": f"chore: upsert {path_in_repo}",
            "content": b64,
            "branch": self.branch,
        }
        if sha:
            body["sha"] = sha
        code, data = self._request(
            "PUT",
            f"/repos/{self.repo}/contents/{path_in_repo}",
            body,
        )
        if code in (200, 201):
            return True, ""
        return False, data.get("error", f"HTTP {code}")

    # ------------------------------------------------------------------ #
    # Walk + push
    # ------------------------------------------------------------------ #
    def _should_skip_dir(self, name: str) -> bool:
        return name in SKIP_DIRS or name.startswith(".")

    def _iter_files(self, root: Path):
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not self._should_skip_dir(d)]
            for fn in filenames:
                if fn in SKIP_FILES:
                    continue
                yield Path(dirpath) / fn

    def push_project(self, project_root: Path,
                     repo_subdir: str = "") -> PushResult:
        ok = self.ensure_repo(private=True, description="BardomPro APK Generator")
        if not ok:
            return PushResult(
                ok=False, repo=self.repo, branch=self.branch,
                files_pushed=0, files_skipped=0, files_failed=0,
                errors=["failed to create/verify repo"],
            )
        pushed = 0
        skipped = 0
        failed = 0
        errors: list[str] = []
        for local_path in self._iter_files(project_root):
            rel = local_path.relative_to(project_root)
            path_in_repo = f"{repo_subdir}/{rel.as_posix()}" if repo_subdir else rel.as_posix()
            ok, err = self.upsert_file(local_path, path_in_repo)
            if ok:
                pushed += 1
            elif "file too large" in err or "too large" in err:
                skipped += 1
            else:
                failed += 1
                if len(errors) < 10:
                    errors.append(f"{path_in_repo}: {err}")
        return PushResult(
            ok=True, repo=self.repo, branch=self.branch,
            files_pushed=pushed, files_skipped=skipped,
            files_failed=failed, errors=errors,
            commit_url=f"https://github.com/{self.repo}/tree/{self.branch}",
        )

    def push_folder(self, folder: Path, repo_subdir: str) -> PushResult:
        """Push a single folder to <repo_subdir>/ in the repo."""
        return self.push_project(folder, repo_subdir)


if __name__ == "__main__":
    import sys
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = sys.argv[1] if len(sys.argv) > 1 else "abuhoney/apk-generator-system"
    target = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".")
    if not token:
        print("GITHUB_TOKEN env var required")
        sys.exit(1)
    gh = GitHubClient(token, repo)
    res = gh.push_project(target)
    print(json.dumps(res.to_dict(), indent=2))
