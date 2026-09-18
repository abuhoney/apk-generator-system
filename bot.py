#!/usr/bin/env python3
"""
bot.py — BardomPro Telegram Bot (from bardom-platform v17 pattern).

Uses Pyrogram for the bot + requests for Firebase REST.
Runs alongside the Flask backend (separate process).

Bot commands:
    /start       — Link account or reward link
    /link        — Linking instructions
    /points      — Show balance
    /functions   — List dynamic functions
    /invite      — Generate invite link
    /inbox       — Show messages
    /buy         — Buy points with Stars
    /build <fn>  — Build an APK for a function
    /cancel      — Cancel pending operation
    /add_points  — Admin: add points
    /newfunc     — Admin: create function
    /announce    — Admin: broadcast

Run:  python3 bot.py
Stop: Ctrl+C
"""
from __future__ import annotations

import os
import sys
import json
import asyncio
import logging
import urllib.request
import urllib.parse
from pathlib import Path

# Add backend to path for config access
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
from engine.config import get_config

# ---------- Logging ----------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger("BardomBot")

# ---------- Config ----------
cfg = get_config()
API_ID = int(cfg.telegram_api_id or 0)
API_HASH = cfg.telegram_api_hash or ""
BOT_TOKEN = cfg.telegram_bot_token or ""
ADMIN_ID = int(cfg.telegram_admin_chat_id or 0)
FIREBASE_URL = cfg.firebase_database_url or ""
BACKEND_URL = cfg.backend_url or ""

logger.info(f"Bot starting — admin={ADMIN_ID}, backend={BACKEND_URL}")


# ---------- Firebase REST helpers (no SDK) ----------
def fb_get(path: str):
    try:
        url = f"{FIREBASE_URL}{path}.json"
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.loads(r.read() or "null")
    except Exception as e:
        logger.error(f"fb_get {path}: {e}")
        return None


def fb_put(path: str, data):
    try:
        url = f"{FIREBASE_URL}{path}.json"
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="PUT")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read() or "null")
    except Exception as e:
        logger.error(f"fb_put {path}: {e}")
        return None


def fb_patch(path: str, data):
    try:
        url = f"{FIREBASE_URL}{path}.json"
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="PATCH")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read() or "null")
    except Exception as e:
        logger.error(f"fb_patch {path}: {e}")
        return None


# ---------- Backend API helpers ----------
def backend_build_apk(function_name: str) -> dict:
    """Call the backend's /api/build-apk endpoint."""
    try:
        url = f"{BACKEND_URL}/api/build-apk"
        body = json.dumps({"function": function_name}).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read() or "{}")
    except Exception as e:
        return {"ok": False, "error": str(e)}


def backend_list_functions() -> list:
    """Call the backend's /api/functions endpoint."""
    try:
        url = f"{BACKEND_URL}/api/functions"
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read() or "{}")
            return data.get("functions", [])
    except Exception:
        return []


# ---------- Bot logic (uses Telegram Bot API directly — no Pyrogram needed) ----------
def send_message(chat_id: int, text: str, parse_mode: str = "Markdown") -> dict:
    """Send a message via the Telegram Bot API."""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        body = json.dumps({
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or "{}")
    except Exception as e:
        logger.error(f"send_message: {e}")
        return {"ok": False, "error": str(e)}


def send_document(chat_id: int, file_path: str, caption: str = "") -> dict:
    """Send a document (APK) via multipart form."""
    try:
        import mimetypes
        boundary = "----BardomBoundary" + os.urandom(8).hex()
        body = b""
        # chat_id field
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="chat_id"\r\n\r\n'.encode()
        body += f"{chat_id}\r\n".encode()
        # caption field
        if caption:
            body += f"--{boundary}\r\n".encode()
            body += f'Content-Disposition: form-data; name="caption"\r\n\r\n'.encode()
            body += f"{caption}\r\n".encode()
        # file
        content = Path(file_path).read_bytes()
        mime = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
        body += f"--{boundary}\r\n".encode()
        body += (
            f'Content-Disposition: form-data; name="document"; '
            f'filename="{Path(file_path).name}"\r\n'
            f'Content-Type: {mime}\r\n\r\n'
        ).encode()
        body += content + b"\r\n"
        body += f"--{boundary}--\r\n".encode()

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read() or "{}")
    except Exception as e:
        logger.error(f"send_document: {e}")
        return {"ok": False, "error": str(e)}


# ---------- Command handlers ----------
def cmd_start(chat_id: int, user_id: int, args: list) -> str:
    # Check if there's a referral code
    if args:
        ref_code = args[0]
        # Link this user with the referrer
        fb_patch(f"/users/{user_id}", {"referred_by": ref_code})
        send_message(chat_id, f"Welcome! You were referred by `{ref_code}`.")
    else:
        send_message(chat_id,
            "Welcome to *BardomPro*!\n\n"
            "I can build unlimited APKs for you.\n\n"
            "Commands:\n"
            "  /functions — List available functions\n"
            "  /build calculator — Build a calculator APK\n"
            "  /points — Show your points\n"
            "  /help — Show all commands")


def cmd_functions(chat_id: int) -> str:
    fns = backend_list_functions()
    if not fns:
        send_message(chat_id, "No functions available. Backend may be offline.")
        return
    text = "*Available Functions:*\n\n"
    for fn in fns:
        manifest = fn.get("manifest", {})
        text += f"  • `{fn['name']}` — {manifest.get('name', fn['name'])}\n"
        text += f"    {manifest.get('description', '')}\n\n"
    text += "\nUse `/build <name>` to build an APK."
    send_message(chat_id, text)


def cmd_build(chat_id: int, args: list) -> str:
    if not args:
        send_message(chat_id, "Usage: `/build <function_name>`\nExample: `/build calculator`")
        return
    fn_name = args[0]
    send_message(chat_id, f"Building APK for `{fn_name}`...\nThis may take 30-60 seconds.")
    result = backend_build_apk(fn_name)
    if result.get("success"):
        apk_url = result.get("apk_path", "").replace("/opt/render/project/src", BACKEND_URL)
        # The backend stores APKs at /download/<fn>/<filename>
        app_name = result.get("manifest", {}).get("app_name", fn_name)
        download_url = f"{BACKEND_URL}/download/{fn_name}/{app_name}.apk"
        send_message(chat_id,
            f"✅ *APK built successfully!*\n\n"
            f"Function: `{fn_name}`\n"
            f"Size: {result.get('apk_size', 0)} bytes\n"
            f"Mode: `{result.get('build_mode', 'unknown')}`\n\n"
            f"[Download APK]({download_url})")
    else:
        send_message(chat_id, f"❌ Build failed: {result.get('error', 'unknown error')}")


def cmd_points(chat_id: int, user_id: int) -> str:
    user = fb_get(f"/users/{user_id}")
    points = (user or {}).get("points", 0)
    send_message(chat_id, f"Your balance: *{points}* points")


def cmd_help(chat_id: int) -> str:
    send_message(chat_id,
        "*BardomPro Bot Commands*\n\n"
        "  /start — Welcome\n"
        "  /functions — List functions\n"
        "  /build <name> — Build an APK\n"
        "  /points — Show balance\n"
        "  /inbox — Show messages\n"
        "  /invite — Generate invite link\n\n"
        "_Admin commands:_\n"
        "  /add_points <uid> <amount>\n"
        "  /newfunc <id> <type> <title> <cost>\n"
        "  /announce <text>")


def cmd_announce(chat_id: int, user_id: int, args: list) -> str:
    if user_id != ADMIN_ID:
        send_message(chat_id, "Admin only.")
        return
    text = " ".join(args)
    if not text:
        send_message(chat_id, "Usage: `/announce <text>`")
        return
    fb_put("/announcements/latest", {
        "text": text,
        "by": user_id,
        "at": datetime.utcnow().isoformat() if 'datetime' in dir() else "",
    })
    send_message(chat_id, "✅ Announcement sent.")


# ---------- Long-polling loop ----------
def process_update(update: dict):
    """Process a single Telegram update."""
    message = update.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    user_id = message.get("from", {}).get("id")
    text = message.get("text", "")

    if not chat_id or not text:
        return

    parts = text.split()
    cmd = parts[0].lower()
    args = parts[1:]

    logger.info(f"Command: {cmd} from user {user_id} in chat {chat_id}")

    if cmd == "/start":
        cmd_start(chat_id, user_id, args)
    elif cmd == "/functions":
        cmd_functions(chat_id)
    elif cmd == "/build":
        cmd_build(chat_id, args)
    elif cmd == "/points":
        cmd_points(chat_id, user_id)
    elif cmd == "/help":
        cmd_help(chat_id)
    elif cmd == "/announce":
        cmd_announce(chat_id, user_id, args)
    else:
        send_message(chat_id, f"Unknown command: {cmd}\nType /help for commands.")


def get_updates(offset: int = 0) -> list:
    """Long-poll Telegram for updates."""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
        body = json.dumps({
            "offset": offset,
            "timeout": 30,
            "limit": 10,
        }).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read() or "{}")
            return data.get("result", [])
    except Exception as e:
        logger.error(f"get_updates: {e}")
        return []


def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set in .env")
        sys.exit(1)

    logger.info("Bot started. Press Ctrl+C to stop.")
    offset = 0
    while True:
        updates = get_updates(offset)
        for update in updates:
            offset = update.get("update_id", offset) + 1
            try:
                process_update(update)
            except Exception as e:
                logger.error(f"process_update: {e}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped.")
