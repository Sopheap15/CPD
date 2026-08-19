"""Shared helpers used by every conversation handler."""

from __future__ import annotations

import logging
import time
from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from cpd.config import ADMIN_IDS, BOT_ICON
from cpd.constants import NL
from cpd.i18n import fmt, t
from cpd.services.data_loader import CpdData

logger = logging.getLogger(__name__)


def _cpd(context: ContextTypes.DEFAULT_TYPE) -> CpdData:
    """Return the shared, auto-reloading data object."""
    data = context.bot_data.setdefault("cpd", CpdData())
    data.ensure_loaded()
    return data


async def safe_reply_html(update: Update, text: str, **kwargs) -> None:
    """Reply with HTML, falling back to a generic message on network errors."""
    try:
        await update.effective_message.reply_html(text, **kwargs)
    except Exception:  # noqa: BLE001 - Telegram connectivity/API errors
        logger.warning("Failed to send message (network issue): %s", type(text).__name__)
        try:
            await update.effective_message.reply_text(t("error"))
        except Exception:  # noqa: BLE001 - never cascade another failure
            logger.warning("Even the error fallback failed to send")


def _is_admin(update: Update) -> bool:
    """True when the sender is one of the configured admin Telegram IDs."""
    return update.effective_user.id in ADMIN_IDS


def menu_keyboard() -> InlineKeyboardMarkup:
    """Menu shown under every CPD report."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📊 សង្ខេប (Summary)", callback_data="menu|summary"),
                InlineKeyboardButton("🎓 បណ្តុះបណ្តាល (Training)", callback_data="menu|training"),
            ],
            [
                InlineKeyboardButton("📜 វិញ្ញាបនបត្រ (Certificate)", callback_data="menu|certificate"),
                InlineKeyboardButton("🔍 ស្វែងរកផ្សេងទៀត (Search)", callback_data="menu|search"),
            ],
            [
                InlineKeyboardButton("រួចរាល់", callback_data="menu|done"),
            ],
        ]
    )


def _start_keyboard() -> InlineKeyboardMarkup:
    """Main /start menu."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "📋 ចុះឈ្មោះវគ្គបណ្តុះបណ្តាល (Register for Course)",
            callback_data="start|register")],
        [InlineKeyboardButton(
            "📊 មើលប្រវត្តិ CPD (View CPD History)",
            callback_data="start|view_cpd")],
    ])


async def send_start_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int,
                             extra: str = "") -> None:
    """Send the bot icon (if any) followed by the welcome + commands message."""
    keyboard = _start_keyboard()
    text = f"<b>{t('welcome')}</b>"
    if extra:
        text += "\n\n" + extra

    try:
        if BOT_ICON:
            with open(BOT_ICON, "rb") as fh:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=fh,
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
    except Exception:  # noqa: BLE001 - fall back to plain welcome on any error
        try:
            await context.bot.send_message(chat_id, t("welcome"),
                                           reply_markup=keyboard)
        except Exception:
            pass


def clear_registration_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Drop all half-finished registration data for this user."""
    for key in ("reg_course_id", "reg_course", "reg_license",
                "reg_name", "reg_phone", "reg_location", "reg_participant"):
        context.user_data.pop(key, None)


def _resolve_for_name(data: CpdData, name: str):
    """Exact participant, else a minimal trainings/certificates-only record."""
    from cpd.services.search import exact_participant
    participant = exact_participant(data.participants, name)
    if participant is not None:
        return participant
    return _name_only_participant(data, name)


def _name_only_participant(data: CpdData, name: str):
    """Create a minimal participant record when none exists in the master list.

    This keeps the bot working when a participant only appears in the
    trainings/certificates files but not in participants.xlsx.
    """
    from cpd.services.data_loader import Participant
    from cpd.services.search import normalize_name

    norm_query = normalize_name(name)

    for t_rec in data.trainings:
        if normalize_name(t_rec.participant_name) == norm_query:
            return Participant(participant_id=t_rec.participant_id, name=name)
    for c_rec in data.certificates:
        if normalize_name(c_rec.participant_name) == norm_query or \
                normalize_name(c_rec.khmer_name) == norm_query:
            return Participant(
                participant_id=c_rec.participant_id,
                name=c_rec.participant_name or name,
                khmer_name=c_rec.khmer_name,
            )
    return Participant(participant_id="", name=name)


def now_str(fmt_str: str = "%Y-%m-%d %H:%M") -> str:
    """Current local time as a string (default: 'YYYY-MM-DD HH:MM')."""
    return time.strftime(fmt_str)


__all__ = [
    "NL",
    "safe_reply_html",
    "_is_admin",
    "menu_keyboard",
    "_start_keyboard",
    "send_start_message",
    "clear_registration_state",
    "_resolve_for_name",
    "_name_only_participant",
    "now_str",
    "escape",
]
