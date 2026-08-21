"""Configuration loading (bot token, data folder, etc.)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

PROJECT_DIR = BASE_DIR
DATA_DIR = Path(os.getenv("CPD_DATA_DIR", BASE_DIR / "data"))

# Bot icon image shown with the /start welcome message.
# Looked up first from CPD_BOT_ICON, then icon/ inside the project folder.
BOT_ICON = os.getenv("CPD_BOT_ICON", "")
if not BOT_ICON:
    _icon_dir = BASE_DIR / "icon"
    _icons = sorted(_icon_dir.glob("*.{png,jpg,jpeg,webp}")) if _icon_dir.is_dir() else []
    BOT_ICON = str(_icons[0]) if _icons else ""

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Comma-separated Telegram user IDs that are allowed to use admin commands.
# e.g. ADMIN_IDS=123456789,987654321
ADMIN_IDS: set[int] = set(
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
)

# Network resilience when api.telegram.org is slow or blocked. Set
# TELEGRAM_PROXY to a SOCKS5/HTTP proxy URL (e.g. socks5://127.0.0.1:1080)
# to route Telegram traffic through it.
TELEGRAM_PROXY = os.getenv("TELEGRAM_PROXY", "").strip()
# Alternative Telegram Bot API endpoint (e.g. a Cloudflare Worker proxy) used
# when api.telegram.org is unreachable. Must end with "/bot".
TELEGRAM_API_BASE_URL = os.getenv("TELEGRAM_API_BASE_URL", "").strip()
TELEGRAM_READ_TIMEOUT = float(os.getenv("TELEGRAM_READ_TIMEOUT", "30"))
TELEGRAM_CONNECT_TIMEOUT = float(os.getenv("TELEGRAM_CONNECT_TIMEOUT", "30"))


def validate() -> None:
    """Raise a clear error if required configuration is missing."""
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set. "
            "Create a bot with @BotFather, then copy .env.example to .env "
            "and paste your token there."
        )