"""
telegram_bot.py — Sends messages and APK files via Telegram bot.

Uses the Telegram Bot API directly (no third-party dependency).
"""
from __future__ import annotations

import os
import json
import urllib.request
import urllib.error
import mimetypes
from pathlib import Path
from typing import Optional


TG_API = "https://api.telegram.org/bot{token}/{method}"


class TelegramBot:
    def __init__(self, token: str, admin_chat_id: str) -> None:
        self.token = token
        self.admin_chat_id = admin_chat_id

    def _request(self, method: str, data: dict,
                 files: Optional[dict] = None) -> dict:
        url = TG_API.format(token=self.token, method=method)
        if files:
            # Multipart form
            boundary = "----BardomBoundary" + os.urandom(8).hex()
            body = b""
            for k, v in data.items():
                body += f"--{boundary}\r\n".encode()
                body += f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode()
                body += f"{v}\r\n".encode()
            for fname, fpath in files.items():
                content = Path(fpath).read_bytes()
                mime = mimetypes.guess_type(fpath)[0] or "application/octet-stream"
                body += f"--{boundary}\r\n".encode()
                body += (
                    f'Content-Disposition: form-data; name="{fname}"; '
                    f'filename="{Path(fpath).name}"\r\n'
                    f'Content-Type: {mime}\r\n\r\n'
                ).encode()
                body += content + b"\r\n"
            body += f"--{boundary}--\r\n".encode()
            req = urllib.request.Request(url, data=body, method="POST")
            req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        else:
            body = json.dumps(data).encode("utf-8")
            req = urllib.request.Request(url, data=body, method="POST")
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read() or "{}")
        except urllib.error.HTTPError as e:
            return {"ok": False, "error": e.read().decode("utf-8", errors="replace")}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def send_message(self, text: str, chat_id: Optional[str] = None) -> dict:
        return self._request("sendMessage", {
            "chat_id": chat_id or self.admin_chat_id,
            "text": text,
            "parse_mode": "Markdown",
        })

    def send_document(self, file_path: Path, caption: str = "",
                      chat_id: Optional[str] = None) -> dict:
        return self._request("sendDocument", {
            "chat_id": chat_id or self.admin_chat_id,
            "caption": caption,
        }, files={"document": str(file_path)})

    def send_apk(self, apk_path: Path, function: str = "",
                 chat_id: Optional[str] = None) -> dict:
        caption = f"📦 *APK built*\nFunction: `{function}`\nFile: `{apk_path.name}`"
        return self.send_document(apk_path, caption=caption, chat_id=chat_id)


if __name__ == "__main__":
    import sys
    bot = TelegramBot(os.environ.get("BOT_TOKEN", ""), os.environ.get("TELEGRAM_ADMIN_CHAT_ID", ""))
    print(json.dumps(bot.send_message("Hello from BardomPro APK Generator"), indent=2))
