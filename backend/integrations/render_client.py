"""
render_client.py — Triggers deploys and checks status on Render.

Uses the Render REST API directly (no third-party dependency).
"""
from __future__ import annotations

import os
import json
import urllib.request
import urllib.error
from typing import Optional


RENDER_API = "https://api.render.com/v1"


class RenderClient:
    def __init__(self, api_key: str, service_id: str) -> None:
        self.api_key = api_key
        self.service_id = service_id
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, body: Optional[dict] = None) -> tuple[int, dict]:
        url = f"{RENDER_API}{path}"
        data = json.dumps(body).encode("utf-8") if body else None
        req = urllib.request.Request(url, data=data, method=method)
        for k, v in self._headers.items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
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

    def health(self) -> dict:
        if not self.api_key or not self.service_id:
            return {"status": "not configured"}
        code, data = self._request("GET", f"/services/{self.service_id}")
        if code == 200:
            return {
                "status": data.get("status", "unknown"),
                "service": data.get("name", self.service_id),
                "type": data.get("type"),
                "url": data.get("serviceDetails", {}).get("url"),
            }
        return {"status": "error", "error": data}

    def deploy(self) -> dict:
        if not self.api_key or not self.service_id:
            return {"ok": False, "error": "Render not configured"}
        code, data = self._request(
            "POST",
            f"/services/{self.service_id}/deploys",
            body={"clearCache": "clear"},
        )
        if code in (200, 201):
            return {
                "ok": True,
                "deploy_id": data.get("id"),
                "status": data.get("status"),
                "commit": data.get("commit", {}).get("id") if isinstance(data.get("commit"), dict) else None,
            }
        return {"ok": False, "error": data}

    def list_deploys(self, limit: int = 5) -> dict:
        code, data = self._request(
            "GET",
            f"/services/{self.service_id}/deploys?limit={limit}",
        )
        if code == 200:
            return {"ok": True, "deploys": data}
        return {"ok": False, "error": data}

    def suspend(self) -> dict:
        code, data = self._request("POST", f"/services/{self.service_id}/suspend", body={})
        if code in (200, 201, 204):
            return {"ok": True}
        return {"ok": False, "error": data}

    def resume(self) -> dict:
        code, data = self._request("POST", f"/services/{self.service_id}/resume", body={})
        if code in (200, 201, 204):
            return {"ok": True}
        return {"ok": False, "error": data}


if __name__ == "__main__":
    import sys
    rc = RenderClient(os.environ.get("RENDER_API_KEY", ""), os.environ.get("RENDER_SERVICE_ID", ""))
    print(json.dumps(rc.health(), indent=2))
