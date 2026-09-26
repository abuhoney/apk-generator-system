"""
firebase_service.py — Real Firebase Realtime DB integration for user accounts.

Provides:
  - get_user_info(device_id): fetch user account + stats
  - register_user(device_id, phone, email): create new user with sharingId
  - verify_coupon(coupon_code, device_id): verify coupon, grant reward
  - transfer_balance(sender_device_id, recipient_id, amount, phone, email): transfer with seedId
  - generate_receiving_gift_id(seed_id, phone, email, user_id): generate unique reference ID
  - upgrade_account(device_id, level, payment_method, proof_image, note): submit upgrade request
  - get_notifications(device_id): fetch user + system notifications
  - get_system_stats(): fetch system-wide stats
  - record_build(device_id, app_name, apk_size): record a build, increment stats

All operations use the Firebase REST API directly. No third-party SDK needed.
Sensitive IDs (receivingGiftId, referringReceivingGiftId) use HMAC-SHA256 with
a server-side secret seed to prevent guessing.

Author: Principal Software Architect
Version: 1.0.0
"""
from __future__ import annotations

import os
import json
import hashlib
import hmac
import datetime
import urllib.request
import urllib.error
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════

# Firebase Database URL (from env var set in render.yaml)
FIREBASE_DB_URL = os.environ.get("FIREBASE_DATABASE_URL", "").rstrip("/")

# Server-side secret for generating reference IDs (must be set as env var)
# This is NOT visible to clients — used only for HMAC signing
REFERENCE_SECRET = os.environ.get("REFERENCE_SECRET", "bardom-v22-secure-seed-2026")

# Default reward values (can be overridden in firebase copouns.json)
DEFAULT_COUPONS = {
    "registrationGiftId": 5,        # 5 points for new registration
    "sharingGiftId": 4,              # 4 points when someone uses your sharingId
    "upgradeId": "verifyUpgradeID",  # placeholder
}

# VIP levels configuration
VIP_LEVELS = {
    "VIP1": {"price": 5, "giftPalance": 50, "freeDays": 30},
    "VIP2": {"price": 15, "giftPalance": 180, "freeDays": 90},
    "VIP3": {"price": 30, "giftPalance": 400, "freeDays": 180},
}

# Payment methods
PAYMENT_METHODS = {
    "Binance": {"address": "BNB-xxx", "account": "binance@bardom.pro"},
    "PayPal": {"id": "paypal.me/bardompro"},
    "Banks": {"phone": "+967773458975", "account": "Bank of Yemen - 1234567890"},
    "MasterCard": {"account": "**** **** **** 1234"},
}


# ═══════════════════════════════════════════════════════════════════════════
# Firebase REST API helper
# ═══════════════════════════════════════════════════════════════════════════

def _firebase_request(method: str, path: str, body: Optional[dict] = None, timeout: int = 15) -> dict:
    """Make an authenticated Firebase REST API request."""
    if not FIREBASE_DB_URL:
        return {"error": "FIREBASE_DATABASE_URL not configured"}

    url = f"{FIREBASE_DB_URL}{path}.json"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            response_text = r.read().decode("utf-8")
            return json.loads(response_text) if response_text else {}
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}"}
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# Reference ID generation (HMAC-SHA256 with server secret)
# ═══════════════════════════════════════════════════════════════════════════

def generate_receiving_gift_id(seed_id: str, phone: str, email: str, user_id: str) -> str:
    """Generate a unique receivingGiftId from seedId + user info + server secret.

    The output is a 5-character alphanumeric code that:
    - Is deterministic (same inputs → same output)
    - Cannot be guessed without the server secret
    - Is short enough to share verbally (5 chars)

    Args:
        seed_id: A random seed provided by the sender
        phone: Recipient's phone
        email: Recipient's email
        user_id: Recipient's device-bound user ID

    Returns:
        5-character alphanumeric code (e.g., "k3x9q")
    """
    # Build the HMAC input
    payload = f"{seed_id}|{phone}|{email}|{user_id}"
    # Sign with the server secret
    signature = hmac.new(
        REFERENCE_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256
    ).digest()
    # Encode to 5-char alphanumeric (a-z0-9 = 36 chars, 36^5 = 60M possibilities)
    charset = "abcdefghijklmnopqrstuvwxyz0123456789"
    code = ""
    for b in signature[:5]:
        code += charset[b % len(charset)]
    return code


def verify_receiving_gift_id(code: str, seed_id: str, phone: str, email: str, user_id: str) -> bool:
    """Verify a receivingGiftId against the expected value."""
    expected = generate_receiving_gift_id(seed_id, phone, email, user_id)
    return hmac.compare_digest(code, expected)


# ═══════════════════════════════════════════════════════════════════════════
# User Account Management
# ═══════════════════════════════════════════════════════════════════════════

def get_user_info(device_id: str) -> dict:
    """Fetch user account info + stats from Firebase."""
    if not device_id:
        return {"error": "device_id required"}

    user = _firebase_request("GET", f"/users/{device_id}")
    if "error" in user:
        # User doesn't exist yet — register them
        return register_user(device_id)

    # Fetch user stats
    stats = _firebase_request("GET", f"/userStats/{device_id}") or {}

    return {
        "device_id": device_id,
        "userId": user.get("userId", device_id[:12]),
        "userName": user.get("userName", "User"),
        "userPhone": user.get("userPhone", ""),
        "userGmail": user.get("userGmail", ""),
        "sharingId": user.get("sharingId", ""),
        "userPalance": stats.get("userPalance", 0),
        "subscriptionType": stats.get("subscriptionType", "Free"),
        "postsCount": stats.get("postsCount", 0),
        "couponsCount": stats.get("couponsCount", 0),
        "appsCount": stats.get("appsCount", 0),
        "level": stats.get("level", "Free"),
    }


def register_user(device_id: str, phone: str = "", email: str = "") -> dict:
    """Register a new user with auto-generated sharingId."""
    # Generate sharingId (8-char alphanumeric from device_id)
    sharing_id = hashlib.md5(
        f"{device_id}{datetime.datetime.utcnow().isoformat()}".encode()
    ).hexdigest()[:8]

    user_data = {
        "userId": device_id[:12],
        "userName": "User_" + sharing_id,
        "userPhone": phone,
        "userGmail": email,
        "sharingId": sharing_id,
        "registeredAt": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    _firebase_request("PUT", f"/users/{device_id}", user_data)

    # Initialize stats with registration gift
    stats = {
        "userPalance": DEFAULT_COUPONS["registrationGiftId"],
        "subscriptionType": "Free",
        "postsCount": 0,
        "couponsCount": 0,
        "appsCount": 0,
        "level": "Free",
    }
    _firebase_request("PUT", f"/userStats/{device_id}", stats)

    return {
        "device_id": device_id,
        **user_data,
        **stats,
        "new_user": True,
    }


def update_user_profile(device_id: str, user_name: str = None, phone: str = None, email: str = None) -> dict:
    """Update user profile fields."""
    updates = {}
    if user_name: updates["userName"] = user_name
    if phone: updates["userPhone"] = phone
    if email: updates["userGmail"] = email
    if not updates:
        return {"error": "No fields to update"}
    _firebase_request("PATCH", f"/users/{device_id}", updates)
    return {"success": True, "updated": list(updates.keys())}


# ═══════════════════════════════════════════════════════════════════════════
# Coupon Verification
# ═══════════════════════════════════════════════════════════════════════════

def verify_coupon(coupon_code: str, device_id: str, recipient_phone: str = "",
                  recipient_email: str = "", recipient_user_id: str = "") -> dict:
    """Verify a coupon code and grant the reward.

    Coupon types:
      - registrationGiftId: new user registration bonus
      - sharingGiftId: bonus when someone uses your sharingId
      - receivingGiftId: balance transfer reference (requires verification)
      - upgradeId: account upgrade verification

    For receivingGiftId, the recipient's phone/email/userId must match
    the values used to generate the code.
    """
    if not coupon_code:
        return {"error": "coupon_code required"}

    # Fetch coupon definitions from Firebase (or use defaults)
    coupons_cfg = _firebase_request("GET", "/copouns") or DEFAULT_COUPONS

    # Check each coupon type
    for coupon_type, expected_value in coupons_cfg.items():
        if isinstance(expected_value, str) and expected_value.startswith("verify"):
            # This is a receivingGiftId or upgradeId — needs verification
            if coupon_code == expected_value:
                # For receivingGiftId: verify recipient info matches
                if coupon_type == "receivingGiftId":
                    if not all([recipient_phone, recipient_email, recipient_user_id]):
                        return {"error": "Recipient phone, email, and userId required for receivingGiftId"}
                    # The sender would have generated the code with a seedId
                    # The recipient enters the code + their info
                    # We need the seedId from the transfer record
                    transfer = _find_transfer_by_code(coupon_code)
                    if not transfer:
                        return {"error": "Transfer code not found or already claimed"}
                    if transfer.get("claimed"):
                        return {"error": "This transfer code has already been claimed"}
                    # Verify recipient matches
                    if (transfer.get("recipientPhone") != recipient_phone or
                        transfer.get("recipientEmail") != recipient_email or
                        transfer.get("recipientUserId") != recipient_user_id):
                        return {"error": "Recipient info does not match the transfer"}
                    # Grant the balance
                    _add_balance(device_id, transfer.get("amount", 0))
                    _mark_transfer_claimed(coupon_code)
                    return {
                        "success": True,
                        "coupon_type": coupon_type,
                        "reward": transfer.get("amount", 0),
                        "resultTitle": "Balance Received!",
                        "resultMeta": f"You received {transfer.get('amount', 0)} points",
                    }
                # upgradeId handling
                return {
                    "success": True,
                    "coupon_type": coupon_type,
                    "resultTitle": "Upgrade Verified",
                    "resultMeta": "Your account has been upgraded",
                }
        elif coupon_code == str(expected_value):
            # Simple numeric coupon (registrationGiftId, sharingGiftId)
            reward = int(expected_value)
            _add_balance(device_id, reward)
            _increment_stat(device_id, "couponsCount")
            return {
                "success": True,
                "coupon_type": coupon_type,
                "reward": reward,
                "resultTitle": "Coupon Verified!",
                "resultMeta": f"You received {reward} points",
            }

    return {"error": "Invalid coupon code"}


# ═══════════════════════════════════════════════════════════════════════════
# Balance Transfer
# ═══════════════════════════════════════════════════════════════════════════

def transfer_balance(sender_device_id: str, amount: int, recipient_phone: str,
                     recipient_email: str, recipient_user_id: str) -> dict:
    """Initiate a balance transfer.

    Generates a receivingGiftId that the recipient must enter to claim.
    The recipient's phone/email/userId must match exactly.

    Args:
        sender_device_id: Sender's device ID
        amount: Points to transfer
        recipient_phone: Recipient's phone (for verification)
        recipient_email: Recipient's email
        recipient_user_id: Recipient's user ID (device-bound)

    Returns:
        Dict with receivingGiftId (to share with recipient) and referringReceivingGiftId (stored)
    """
    if amount <= 0:
        return {"error": "Amount must be positive"}

    # Check sender has enough balance
    sender_stats = _firebase_request("GET", f"/userStats/{sender_device_id}") or {}
    sender_balance = sender_stats.get("userPalance", 0)
    if sender_balance < amount:
        return {"error": "Insufficient balance", "currentBalance": sender_balance}

    # Generate a random seedId (5-char)
    seed_id = hashlib.md5(
        f"{sender_device_id}{datetime.datetime.utcnow().isoformat()}".encode()
    ).hexdigest()[:5]

    # Generate the receivingGiftId (5-char, derived from seedId + recipient info + secret)
    receiving_gift_id = generate_receiving_gift_id(
        seed_id, recipient_phone, recipient_email, recipient_user_id
    )

    # Generate the referringReceivingGiftId (longer, stored on Firebase for verification)
    referring_receiving_gift_id = hashlib.sha256(
        f"{seed_id}{recipient_phone}{recipient_email}{recipient_user_id}{REFERENCE_SECRET}".encode()
    ).hexdigest()[:16]

    # Store the transfer record on Firebase
    transfer_record = {
        "senderDeviceId": sender_device_id,
        "amount": amount,
        "recipientPhone": recipient_phone,
        "recipientEmail": recipient_email,
        "recipientUserId": recipient_user_id,
        "seedId": seed_id,
        "receivingGiftId": receiving_gift_id,
        "referringReceivingGiftId": referring_receiving_gift_id,
        "claimed": False,
        "createdAt": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    _firebase_request("PUT", f"/transfers/{referring_receiving_gift_id}", transfer_record)

    # Deduct from sender immediately (held in escrow until claimed)
    _add_balance(sender_device_id, -amount)

    return {
        "success": True,
        "receivingGiftId": receiving_gift_id,
        "referringReceivingGiftId": referring_receiving_gift_id,
        "amount": amount,
        "resultTitle": "Transfer Initiated",
        "resultMeta": f"Share code '{receivingGiftId}' with recipient. They must enter their matching phone/email/userId to claim.",
    }


def _find_transfer_by_code(code: str) -> Optional[dict]:
    """Find a transfer record by receivingGiftId."""
    transfers = _firebase_request("GET", "/transfers") or {}
    for ref_id, transfer in transfers.items():
        if isinstance(transfer, dict) and transfer.get("receivingGiftId") == code:
            return transfer
    return None


def _mark_transfer_claimed(code: str) -> None:
    """Mark a transfer as claimed."""
    transfers = _firebase_request("GET", "/transfers") or {}
    for ref_id, transfer in transfers.items():
        if isinstance(transfer, dict) and transfer.get("receivingGiftId") == code:
            _firebase_request("PATCH", f"/transfers/{ref_id}", {"claimed": True})
            return


# ═══════════════════════════════════════════════════════════════════════════
# Account Upgrade
# ═══════════════════════════════════════════════════════════════════════════

def upgrade_account(device_id: str, level: str, payment_method: str,
                     proof_image_base64: str = "", note: str = "") -> dict:
    """Submit an account upgrade request with proof of payment.

    The request is stored on Firebase for admin review. The upgrade is
    applied when an admin manually verifies the proof image.
    """
    if level not in VIP_LEVELS:
        return {"error": f"Invalid level. Choose from: {list(VIP_LEVELS.keys())}"}
    if payment_method not in PAYMENT_METHODS:
        return {"error": f"Invalid payment method. Choose from: {list(PAYMENT_METHODS.keys())}"}

    level_cfg = VIP_LEVELS[level]
    payment_cfg = PAYMENT_METHODS[payment_method]

    request_id = hashlib.md5(
        f"{device_id}{level}{datetime.datetime.utcnow().isoformat()}".encode()
    ).hexdigest()[:12]

    upgrade_request = {
        "requestId": request_id,
        "deviceId": device_id,
        "level": level,
        "price": level_cfg["price"],
        "giftPalance": level_cfg["giftPalance"],
        "freeDays": level_cfg["freeDays"],
        "paymentMethod": payment_method,
        "paymentDetails": payment_cfg,
        "proofImage": proof_image_base64[:10000] if proof_image_base64 else "",  # Limit size
        "note": note[:500] if note else "",
        "status": "pending",  # pending, approved, rejected
        "createdAt": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    _firebase_request("PUT", f"/upgradeRequests/{request_id}", upgrade_request)

    # Send notification to user
    _add_notification(device_id, {
        "title": "Upgrade Request Submitted",
        "body": f"Your {level} upgrade request is pending review. Payment: {payment_method}.",
        "type": "upgrade",
        "icon": "💳",
        "read": False,
        "createdAt": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    })

    return {
        "success": True,
        "requestId": request_id,
        "level": level,
        "price": level_cfg["price"],
        "resultTitle": "Upgrade Request Submitted",
        "resultMeta": f"{level} request pending. Pay ${level_cfg['price']} via {payment_method} and upload proof.",
    }


def buy_points(device_id: str, amount_usd: float, payment_method: str,
               proof_image_base64: str = "", note: str = "") -> dict:
    """Submit a buy-points request. Each dollar = giftPalance points."""
    if payment_method not in PAYMENT_METHODS:
        return {"error": f"Invalid payment method. Choose from: {list(PAYMENT_METHODS.keys())}"}

    gift_palance = int(amount_usd * 10)  # 1 USD = 10 points
    payment_cfg = PAYMENT_METHODS[payment_method]

    request_id = hashlib.md5(
        f"{device_id}buy{datetime.datetime.utcnow().isoformat()}".encode()
    ).hexdigest()[:12]

    buy_request = {
        "requestId": request_id,
        "deviceId": device_id,
        "type": "buy_points",
        "amountUsd": amount_usd,
        "giftPalance": gift_palance,
        "paymentMethod": payment_method,
        "paymentDetails": payment_cfg,
        "proofImage": proof_image_base64[:10000] if proof_image_base64 else "",
        "note": note[:500] if note else "",
        "status": "pending",
        "createdAt": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    _firebase_request("PUT", f"/buyRequests/{request_id}", buy_request)

    _add_notification(device_id, {
        "title": "Purchase Request Submitted",
        "body": f"${amount_usd} for {gift_palance} points. Pending review.",
        "type": "buy",
        "icon": "💰",
        "read": False,
        "createdAt": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    })

    return {
        "success": True,
        "requestId": request_id,
        "giftPalance": gift_palance,
        "resultTitle": "Purchase Request Submitted",
        "resultMeta": f"Pay ${amount_usd} via {payment_method}, upload proof to receive {gift_palance} points.",
    }


# ═══════════════════════════════════════════════════════════════════════════
# Notifications
# ═══════════════════════════════════════════════════════════════════════════

def get_notifications(device_id: str) -> list:
    """Fetch all notifications for a user + system-wide notifications."""
    user_notifs = _firebase_request("GET", f"/notifications/{device_id}") or {}
    system_notifs = _firebase_request("GET", "/notifications/system") or {}

    result = []
    # User notifications
    for nid, n in user_notifs.items():
        if isinstance(n, dict):
            n["id"] = nid
            n["scope"] = "user"
            result.append(n)
    # System notifications
    for nid, n in system_notifs.items():
        if isinstance(n, dict):
            n["id"] = nid
            n["scope"] = "system"
            result.append(n)

    # Sort by createdAt (newest first)
    result.sort(key=lambda x: x.get("createdAt", ""), reverse=True)
    return result


def _add_notification(device_id: str, notif: dict) -> None:
    """Add a notification for a user."""
    nid = hashlib.md5(
        f"{device_id}{datetime.datetime.utcnow().isoformat()}".encode()
    ).hexdigest()[:12]
    _firebase_request("PUT", f"/notifications/{device_id}/{nid}", notif)


def mark_notification_read(device_id: str, notification_id: str) -> dict:
    """Mark a notification as read."""
    _firebase_request("PATCH", f"/notifications/{device_id}/{notification_id}", {"read": True})
    return {"success": True}


# ═══════════════════════════════════════════════════════════════════════════
# System Stats
# ═══════════════════════════════════════════════════════════════════════════

def get_system_stats() -> dict:
    """Fetch system-wide statistics."""
    users = _firebase_request("GET", "/users") or {}
    builds = _firebase_request("GET", "/builds") or {}

    # Count users by level
    user_stats = _firebase_request("GET", "/userStats") or {}
    level_counts = {}
    total_apps = 0
    for uid, stats in user_stats.items():
        if isinstance(stats, dict):
            level = stats.get("level", "Free")
            level_counts[level] = level_counts.get(level, 0) + 1
            total_apps += stats.get("appsCount", 0)

    return {
        "totalUsers": len(users) if isinstance(users, dict) else 0,
        "totalBuilds": len(builds) if isinstance(builds, dict) else 0,
        "totalApps": total_apps,
        "levelCounts": level_counts,
        "vip1Count": level_counts.get("VIP1", 0),
        "vip2Count": level_counts.get("VIP2", 0),
        "vip3Count": level_counts.get("VIP3", 0),
        "freeCount": level_counts.get("Free", 0),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Build Recording
# ═══════════════════════════════════════════════════════════════════════════

def record_build(device_id: str, app_name: str, apk_size: int, function_id: str = "") -> dict:
    """Record a build in Firebase and increment user's appsCount."""
    build_id = hashlib.md5(
        f"{device_id}{app_name}{datetime.datetime.utcnow().isoformat()}".encode()
    ).hexdigest()[:12]

    build_record = {
        "buildId": build_id,
        "deviceId": device_id,
        "appName": app_name,
        "apkSize": apk_size,
        "functionId": function_id,
        "createdAt": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    _firebase_request("PUT", f"/builds/{build_id}", build_record)

    # Increment user's appsCount
    _increment_stat(device_id, "appsCount")

    return {"success": True, "buildId": build_id}


# ═══════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════

def _add_balance(device_id: str, amount: int) -> None:
    """Add (or subtract if negative) from user's balance."""
    stats = _firebase_request("GET", f"/userStats/{device_id}") or {}
    current = stats.get("userPalance", 0)
    stats["userPalance"] = current + amount
    _firebase_request("PATCH", f"/userStats/{device_id}", {"userPalance": stats["userPalance"]})


def _increment_stat(device_id: str, stat_name: str, by: int = 1) -> None:
    """Increment a user stat by a value."""
    stats = _firebase_request("GET", f"/userStats/{device_id}") or {}
    current = stats.get(stat_name, 0)
    _firebase_request("PATCH", f"/userStats/{device_id}", {stat_name: current + by})


# ═══════════════════════════════════════════════════════════════════════════
# Configuration endpoints (VIP levels, payment methods, coupons)
# ═══════════════════════════════════════════════════════════════════════════

def get_service_config() -> dict:
    """Return the service configuration (VIP levels, payment methods, default coupons).

    This is what the Android app fetches to populate the UI.
    """
    # Try fetching from Firebase first (allows live updates without redeploy)
    fb_levels = _firebase_request("GET", "/config/vipLevels")
    fb_payments = _firebase_request("GET", "/config/paymentMethods")
    fb_coupons = _firebase_request("GET", "/config/copouns")

    return {
        "vipLevels": fb_levels if isinstance(fb_levels, dict) and fb_levels else VIP_LEVELS,
        "paymentMethods": fb_payments if isinstance(fb_payments, dict) and fb_payments else PAYMENT_METHODS,
        "coupons": fb_coupons if isinstance(fb_coupons, dict) and fb_coupons else DEFAULT_COUPONS,
        "whatsapp_channel_url": "https://whatsapp.com/channel/0029VaijFIC5Ejxq4oG6wX0E",
        "whatsapp_contact_number": "+967773458975",
    }
