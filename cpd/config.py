"""Configuration loading (bot token, data folder, etc.)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

PROJECT_DIR = BASE_DIR
DATA_DIR = Path(os.getenv("CPD_DATA_DIR", BASE_DIR / "data"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Network resilience when api.telegram.org is slow or blocked. Set
# TELEGRAM_PROXY to a SOCKS5/HTTP proxy URL (e.g. socks5://127.0.0.1:1080)
# to route Telegram traffic through it.
TELEGRAM_PROXY = os.getenv("TELEGRAM_PROXY", "").strip()
TELEGRAM_READ_TIMEOUT = float(os.getenv("TELEGRAM_READ_TIMEOUT", "30"))
TELEGRAM_CONNECT_TIMEOUT = float(os.getenv("TELEGRAM_CONNECT_TIMEOUT", "30"))

# Google Sheets data source (optional). If GOOGLE_SHEET_ID is set, the bot
# reads the Google Form response sheet live through Google's data API - no
# download, no API key. The sheet must be shared with
# "Anyone with the link -> Viewer". If the pickup form lives in a separate
# spreadsheet, set GS_ID_C as well.
GS_ID_R = os.getenv("GS_ID_R", "").strip()
GS_ID_C = os.getenv("GS_ID_C", "").strip()
GOOGLE_SHEET_REFRESH_MINUTES = int(
    os.getenv("GOOGLE_SHEET_REFRESH_MINUTES", "5")
)
GOOGLE_SHEET_SHEET_NAMES = [
    name.strip()
    for name in os.getenv(
        "GOOGLE_SHEET_SHEET_NAMES",
        "Form Responses 1,Form Responses 2,Form Responses 3,Sheet1,Sheet2",
    ).split(",")
    if name.strip()
]


def validate() -> None:
    """Raise a clear error if required configuration is missing."""
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set. "
            "Create a bot with @BotFather, then copy .env.example to .env "
            "and paste your token there."
        )