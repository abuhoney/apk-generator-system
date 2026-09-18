"""
config.py — Central configuration loader for BardomPro APK Generator.

Loads every credential from the environment (or .env file) and exposes
a single `get_config()` that the rest of the engine imports.
"""
from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Optional

# --------------------------------------------------------------------------- #
# Project paths
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parents[2]   # .../apk-generator-system
FUNCTIONS_DIR = PROJECT_ROOT / "functions"
TEMPLATES_DIR = PROJECT_ROOT / "templates"
BUILD_DIR = PROJECT_ROOT / "_builds"
OUTPUT_DIR = PROJECT_ROOT / "_output"
DASHBOARD_DIR = PROJECT_ROOT / "dashboard"
ANDROID_DIR = PROJECT_ROOT / "android"

for _d in (BUILD_DIR, OUTPUT_DIR):
    _d.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
# .env loader (lightweight — no third-party dependency)
# --------------------------------------------------------------------------- #
def _load_dotenv(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        env[key] = value
    return env


_env_file = PROJECT_ROOT / ".env"
_env_data = _load_dotenv(_env_file)
# Promote into os.environ without overwriting existing values
for _k, _v in _env_data.items():
    os.environ.setdefault(_k, _v)


# --------------------------------------------------------------------------- #
# Config object
# --------------------------------------------------------------------------- #
class Config:
    """Holds every credential + path used by the engine."""

    # ----- paths ----- #
    project_root: Path = PROJECT_ROOT
    functions_dir: Path = FUNCTIONS_DIR
    templates_dir: Path = TEMPLATES_DIR
    build_dir: Path = BUILD_DIR
    output_dir: Path = OUTPUT_DIR
    dashboard_dir: Path = DASHBOARD_DIR
    android_dir: Path = ANDROID_DIR

    # ----- Telegram ----- #
    telegram_api_id: str = os.environ.get("API_ID", "")
    telegram_api_hash: str = os.environ.get("API_HASH", "")
    telegram_bot_token: str = os.environ.get("BOT_TOKEN", "")
    telegram_admin_chat_id: str = os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "")
    telegram_bot_username: str = os.environ.get("BOT_USERNAME", "")

    # ----- GitHub ----- #
    github_repo: str = os.environ.get("GITHUB_REPO", "abuhoney/apk")
    github_branch: str = os.environ.get("GITHUB_BRANCH", "main")
    github_token: str = os.environ.get("GITHUB_TOKEN", "")
    new_github_repo: str = os.environ.get("NEW_GITHUB_REPO", "abuhoney/apk-generator-system")
    hf_token: str = os.environ.get("HF_TOKEN", "")

    # ----- Render ----- #
    render_api_key: str = os.environ.get("RENDER_API_KEY", "")
    render_service_id: str = os.environ.get("RENDER_SERVICE_ID", "")

    # ----- Backend ----- #
    backend_url: str = os.environ.get("BACKEND_URL", "")
    backend_secret: str = os.environ.get("BACKEND_SECRET", "")
    node_env: str = os.environ.get("NODE_ENV", "production")
    port: int = int(os.environ.get("PORT", "3000"))

    # ----- Firebase ----- #
    firebase_api_key: str = os.environ.get("FIREBASE_API_KEY", "")
    firebase_app_id: str = os.environ.get("FIREBASE_APP_ID", "")
    firebase_auth_domain: str = os.environ.get("FIREBASE_AUTH_DOMAIN", "")
    firebase_database_url: str = os.environ.get("FIREBASE_DATABASE_URL", "")
    firebase_project_id: str = os.environ.get("FIREBASE_PROJECT_ID", "")

    # ----- Behavior flags ----- #
    auto_push_github: bool = os.environ.get("AUTO_PUSH_GITHUB", "false").lower() == "true"

    # ----- Android SDK (auto-detected at runtime) ----- #
    android_sdk_path: Optional[str] = os.environ.get("ANDROID_SDK_ROOT")
    java_home: Optional[str] = os.environ.get("JAVA_HOME")

    # ----- Build pipeline executables (resolved by setup.sh) ----- #
    aapt2_path: Optional[str] = os.environ.get("AAPT2_PATH")
    javac_path: Optional[str] = os.environ.get("JAVAC_PATH")
    d8_path: Optional[str] = os.environ.get("D8_PATH")
    zipalign_path: Optional[str] = os.environ.get("ZIPALIGN_PATH")
    apksigner_path: Optional[str] = os.environ.get("APKSIGNER_PATH")
    keytool_path: Optional[str] = os.environ.get("KEYTOOL_PATH")

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__class__.__dict__.items()
                if not k.startswith("_") and not callable(v)}

    def safe_dict(self) -> dict:
        """A version with secrets redacted — for API responses."""
        d = self.to_dict().copy()
        for secret in ("telegram_bot_token", "telegram_api_hash", "github_token",
                       "render_api_key", "hf_token", "firebase_api_key", "backend_secret"):
            if d.get(secret):
                d[secret] = "***REDACTED***"
        return d


_cfg = Config()


def get_config() -> Config:
    return _cfg


def reload_config() -> Config:
    global _cfg
    _cfg = Config()
    return _cfg


# --------------------------------------------------------------------------- #
# Persist a paths.json so external scripts (setup.sh, build.sh) can read it
# --------------------------------------------------------------------------- #
def write_paths_json() -> None:
    paths = {
        "project_root": str(PROJECT_ROOT),
        "functions_dir": str(FUNCTIONS_DIR),
        "templates_dir": str(TEMPLATES_DIR),
        "build_dir": str(BUILD_DIR),
        "output_dir": str(OUTPUT_DIR),
        "dashboard_dir": str(DASHBOARD_DIR),
        "android_dir": str(ANDROID_DIR),
        "android_sdk_root": _cfg.android_sdk_path or "",
        "java_home": _cfg.java_home or "",
        "aapt2": _cfg.aapt2_path or "",
        "javac": _cfg.javac_path or "",
        "d8": _cfg.d8_path or "",
        "zipalign": _cfg.zipalign_path or "",
        "apksigner": _cfg.apksigner_path or "",
        "keytool": _cfg.keytool_path or "",
    }
    sdk_cfg = PROJECT_ROOT / "sdk_config" / "paths.json"
    sdk_cfg.parent.mkdir(parents=True, exist_ok=True)
    sdk_cfg.write_text(json.dumps(paths, indent=2), encoding="utf-8")


write_paths_json()
