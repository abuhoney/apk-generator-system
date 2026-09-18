"""
firebase_client.py — Records build metadata in Firebase Realtime DB.

Uses the Firebase REST API directly (no third-party dependency).
"""
from __future__ import annotations

import os
import json
import urllib.request
import urllib.error
import datetime
from typing import Optional


class FirebaseClient:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url.rstrip("/")

    def _request(self, method: str, path: str, body: Optional[dict] = None) -> dict:
        url = f"{self.database_url}{path}.json"
        data = json.dumps(body).encode("utf-8") if body else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read() or "{}")
        except urllib.error.HTTPError as e:
            return {"error": e.read().decode("utf-8", errors="replace")}
        except Exception as e:
            return {"error": str(e)}

    def record_build(self, build_info: dict) -> dict:
        build_info.setdefault("recorded_at",
                               datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z")
        key = build_info.get("function", "unknown") + "-" + datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
        return self._request("PUT", f"/builds/{key}", build_info)

    def list_builds(self) -> dict:
        return self._request("GET", "/builds")

    def list_apps(self) -> dict:
        return self._request("GET", "/apps")

    def register_app(self, app_id: str, info: dict) -> dict:
        return self._request("PUT", f"/apps/{app_id}", info)


if __name__ == "__main__":
    fc = FirebaseClient(os.environ.get("FIREBASE_DATABASE_URL", ""))
    print(json.dumps(fc.list_builds(), indent=2))
