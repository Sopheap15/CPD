"""Telegram bot: receives a participant name and shows CPD history."""

from __future__ import annotations

import logging
from html import escape
from typing import Any, Coroutine

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from cpd.config import TELEGRAM_BOT_TOKEN
from cpd.data_loader import CpdData
from cpd.formatter import (
    certificate_report,
    summary_report,
    summary_sections,
    training_report,
)
from cpd.i18n import fmt, t
from cpd.search import exact_participant, find_best, resolve_participant

logger = logging.getLogger(__name__)

# Conversation states
NAME = "NAME"
MENU = "MENU"

UNKNOWN_CHAT_ID = "___"

NL = "\n"


# ------------------------------------------------------------------ helpers
def _cpd(context: ContextTypes.DEFAULT_TYPE) -> CpdData:
    data = context.bot_data.setdefault("cpd", CpdData())
    data.ensure_loaded()
    return data


def menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("សង្ខេប", callback_data="menu|summary"),
                InlineKeyboardButton("បណ្ដុះបណ្ដាល", callback_data="menu|training"),
                InlineKeyboardButton("វិញ្ញាបនបត្រ", callback_data="menu|certificate"),
            ],
            [
                InlineKeyboardButton("ស្វែងរកផ្សេង", callback_data="menu|search"),
                InlineKeyboardButton("រួចរាល់", callback_data="menu|done"),
            ],
        ]
    )


async def safe_reply_html(update: Update, text: str, **kwargs) -> None:
    try:
        await update.effective_message.reply_html(text, **kwargs)
    except Exception:  # noqa: BLE001 - Telegram connectivity/API errors
        logger.warning("Failed to send message (network issue): %s",
                       type(text).__name__)
        try:
            await update.effective_message.reply_text(t("error"))
        except Exception:  # noqa: BLE001 - never cascade another failure
            logger.warning("Even the error fallback failed to send")


# ----------------------------------------------------------------- commands
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    await safe_reply_html(update, t("welcome"))
    await safe_reply_html(update, t("ask_name"))
    return NAME


async def cmd_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    query = " ".join(context.args).strip() if context.args else ""
    if not query:
        await safe_reply_html(update, t("ask_name"))
        return NAME
    return await _handle_name(update, context, query)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    await safe_reply_html(update, t("help"))
    return ConversationHandler.END


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    context.user_data.pop("name", None)
    await safe_reply_html(update, t("cancel"))
    return ConversationHandler.END


# ------------------------------------------------------------- name lookup
async def on_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    return await _handle_name(update, context, update.effective_message.text or "")


async def _handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str) -> str:
    """Resolve the typed name and reply with a report or a match list."""
    try:
        data = _cpd(context)
    except Exception:  # noqa: BLE001
        await safe_reply_html(update, t("loading_error"))
        return NAME

    if not query.strip():
        await safe_reply_html(update, t("ask_name"))
        return NAME

    chosen, shortlist, _auto = resolve_participant(
        query, data.all_names(), data.participants
    )

    if chosen is None and not shortlist:
        await safe_reply_html(update, fmt("not_found", name=escape(query)))
        return NAME

    if chosen is not None:
        return await _show_summary(update, context, chosen.name)

    # Multiple possibilities -> ask the user to pick one.
    buttons = [
        [InlineKeyboardButton(name, callback_data=f"pick|{name}")] for name in shortlist
    ]
    await safe_reply_html(
        update,
        fmt("multiple_matches", count=len(shortlist)),
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return MENU


# ---------------------------------------------------------------- callback
async def _on_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    query = update.callback_query
    if query is None:
        return MENU
    await query.answer()
    name = query.data.split("|", 1)[1]
    return await _show_summary(update, context, name, edit=True)


async def _on_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str | None:
    query = update.callback_query
    if query is None:
        return None
    await query.answer()
    action = query.data.split("|", 1)[1]

    data = _cpd(context)
    name = context.user_data.get("name", "")
    if not name:
        await query.edit_message_text(t("ask_name"), parse_mode="HTML")
        return NAME

    participant = _resolve_for_name(data, name)
    if participant is None:
        await query.edit_message_text(t("ask_name"), parse_mode="HTML")
        return NAME

    trainings = data.trainings_for(participant.participant_id, participant.name, participant.khmer_name)
    certificates = data.certificates_for(participant.participant_id, participant.name, participant.khmer_name)

    if action == "summary":
        text = summary_report(participant, trainings, certificates)
        markup = menu_keyboard()
    elif action == "training":
        text = training_report(participant.name, trainings)
        markup = menu_keyboard()
    elif action == "certificate":
        text = certificate_report(participant.name, certificates)
        markup = menu_keyboard()
    elif action == "search":
        context.user_data.pop("name", None)
        await query.edit_message_text(t("ask_name"), parse_mode="HTML")
        return NAME
    elif action == "done":
        await query.edit_message_text(t("done"), parse_mode="HTML")
        context.user_data.pop("name", None)

        # A CallbackQueryHandler inside the conversation can end it by
        # returning ConversationHandler.END from within the state handler.
        return ConversationHandler.END
    else:
        return MENU

    try:
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:  # noqa: BLE001 - e.g. message not modified
        await safe_reply_html(update, text, reply_markup=markup)
    return MENU


# -------------------------------------------------------------- show report
async def _show_summary(
    update: Update, context: ContextTypes.DEFAULT_TYPE, name: str, edit: bool = False
) -> str:
    data = _cpd(context)
    participant = _resolve_for_name(data, name)

    context.user_data["name"] = participant.name
    trainings = data.trainings_for(participant.participant_id, participant.name, participant.khmer_name)
    certificates = data.certificates_for(participant.participant_id, participant.name, participant.khmer_name)

    sections = summary_sections(participant, trainings, certificates)
    text = NL.join(sections)

    def _markup():
        return menu_keyboard()

    try:
        if edit:
            await update.callback_query.edit_message_text(
                text, parse_mode="HTML", reply_markup=_markup()
            )
            return MENU

        # New message: send one combined message, or split into sections when
        # the combined report would be too long for a single Telegram message.
        if len(text) <= 3800:
            await update.effective_message.reply_html(text, reply_markup=_markup())
        else:
            for idx, section in enumerate(sections):
                markup = _markup() if idx == len(sections) - 1 else None
                await update.effective_message.reply_html(section, reply_markup=markup)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to send summary for %r: %r", name, exc)
        await safe_reply_html(update, t("error"))
    return MENU


def _resolve_for_name(data, name: str):
    """Exact participant, else a minimal trainings/certificates-only record."""
    participant = exact_participant(data.participants, name)
    if participant is not None:
        return participant
    return _name_only_participant(data, name)


def _name_only_participant(data, name: str):
    """Create a minimal participant record when none exists in the master list.

    This keeps the bot working when a participant only appears in the
    trainings/certificates files but not in participants.xlsx.
    """
    from cpd.data_loader import Participant
    from cpd.search import normalize_name
    
    norm_query = normalize_name(name)

    for t_rec in data.trainings:
        if normalize_name(t_rec.participant_name) == norm_query:
            return Participant(participant_id=t_rec.participant_id, name=name)
    for c_rec in data.certificates:
        if normalize_name(c_rec.participant_name) == norm_query or normalize_name(c_rec.khmer_name) == norm_query:
            return Participant(
                participant_id=c_rec.participant_id,
                name=c_rec.participant_name or name,
                khmer_name=c_rec.khmer_name,
            )
    return Participant(participant_id="", name=name)


# ------------------------------------------------------------------- build
def build_application() -> Application:
    import os

    from cpd.config import (
        TELEGRAM_BOT_TOKEN,
        TELEGRAM_CONNECT_TIMEOUT,
        TELEGRAM_PROXY,
        TELEGRAM_READ_TIMEOUT,
    )

    if TELEGRAM_PROXY:
        # httpx (used by python-telegram-bot) honours these environment
        # variables, letting us route Telegram traffic through a proxy when
        # the API is unreachable.
        os.environ.setdefault("HTTPS_PROXY", TELEGRAM_PROXY)
        os.environ.setdefault("HTTP_PROXY", TELEGRAM_PROXY)

    CONNECT_TIMEOUT = TELEGRAM_CONNECT_TIMEOUT
    READ_TIMEOUT = TELEGRAM_READ_TIMEOUT

    shared_handlers = [
        MessageHandler(filters.TEXT & ~filters.COMMAND, on_name),
        CommandHandler("start", cmd_start),
        CommandHandler("view", cmd_view),
        CommandHandler("cancel", cmd_cancel),
        CallbackQueryHandler(_on_pick, pattern=r"^pick\|"),
        CallbackQueryHandler(_on_menu, pattern=r"^menu\|"),
    ]

    conversation = ConversationHandler(
        entry_points=[
            CommandHandler("start", cmd_start),
            CommandHandler("view", cmd_view),
        ],
        states={
            NAME: shared_handlers,
            MENU: shared_handlers,
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
            CommandHandler("help", cmd_help),
        ],
    )

    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .connect_timeout(CONNECT_TIMEOUT)
        .read_timeout(READ_TIMEOUT)
        .write_timeout(READ_TIMEOUT)
        .pool_timeout(READ_TIMEOUT)
        .build()
    )
    application.add_handler(conversation)
    application.add_error_handler(_error_handler)
    return application


async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled error (update=%s): %s",
                 type(update).__name__, context.error, exc_info=context.error)


def main() -> None:
    import warnings

    warnings.filterwarnings(
        "ignore",
        message="If 'per_message=False'.*",
    )

    from cpd.config import TELEGRAM_BOT_TOKEN, validate

    validate()

    class _ScrubFormatter(logging.Formatter):
        """Never let the bot token leak into any log line."""

        def __init__(self, fmt: str | None = None, secrets: tuple[str, ...] = ()):
            super().__init__(fmt=fmt or "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            self.secrets = tuple(s for s in secrets if s)

        def format(self, record: logging.LogRecord) -> str:
            text = super().format(record)
            for secret in self.secrets:
                text = text.replace(secret, "<redacted>")
            return text

    _handler = logging.StreamHandler()
    _handler.setFormatter(_ScrubFormatter(secrets=(TELEGRAM_BOT_TOKEN,)))
    logging.basicConfig(level=logging.INFO, handlers=[_handler])

    # httpx logs the full request URL (which embeds the token) at INFO level.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    for name in ("urllib3", "http.client"):
        logging.getLogger(name).setLevel(logging.WARNING)

    logger.info("Starting CPD Track bot (polling)…")
    app = build_application()
    app.run_polling()


if __name__ == "__main__":
    main()