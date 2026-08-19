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
COURSE_REGISTRATION_LINK = os.getenv("COURSE_REGISTRATION_LINK", "https://forms.gle/dummy_link")

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

# --- Bakong KHQR payment settings ---
# Merchant Bakong Account ID (e.g. "merchant@aclb"), the merchant display
# name shown on the QR, and the Bakong developer token (register at
# https://api-bakong.nbc.gov.kh/register). Payments are captured in USD.
BAKONG_ACCOUNT_ID = os.getenv("BAKONG_ACCOUNT_ID", "").strip()
BAKONG_MERCHANT_NAME = os.getenv("BAKONG_MERCHANT_NAME", "").strip()
BAKONG_MERCHANT_CITY = os.getenv("BAKONG_MERCHANT_CITY", "Phnom Penh").strip()
BAKONG_CURRENCY = os.getenv("BAKONG_CURRENCY", "USD").strip().upper()
BAKONG_TOKEN = os.getenv("BAKONG_TOKEN", "").strip()
# Email used to register at https://api-bakong.nbc.gov.kh/register. When set,
# the bot can renew its own token via POST /v1/renew_token and never needs a
# manually pasted token again.
BAKONG_EMAIL = os.getenv("BAKONG_EMAIL", "").strip()
# Bakong Open API base URL (production). Endpoints under it are called with
# the renewal script and the transaction-polling job.
BAKONG_BASE_URL = os.getenv("BAKONG_BASE_URL", "https://api-bakong.nbc.gov.kh").strip().rstrip("/")
# Renew the developer token whenever it expires within this many days
# (tokens are valid ~90 days; the job runs on this same cadence).
BAKONG_TOKEN_RENEW_DAYS = int(os.getenv("BAKONG_TOKEN_RENEW_DAYS", "24"))
# How long (minutes) to keep polling Bakong for a payment before giving up.
BAKONG_PAYMENT_TIMEOUT_MINUTES = int(
    os.getenv("BAKONG_PAYMENT_TIMEOUT_MINUTES", "15")
)


def validate() -> None:
    """Raise a clear error if required configuration is missing."""
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set. "
            "Create a bot with @BotFather, then copy .env.example to .env "
            "and paste your token there."
        )