"""CPD history lookup: name/ID/phone resolution and report menus."""

from __future__ import annotations

import logging
from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from cpd.constants import MENU, NAME, NL
from cpd.services.formatter import (
    certificate_report,
    summary_sections,
)
from cpd.handlers.common import (
    _is_admin,
    _resolve_for_name,
    menu_keyboard,
    safe_reply_html,
)
from cpd.i18n import fmt, t

logger = logging.getLogger(__name__)


async def cmd_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    from cpd.services.storage import get_linked_name
    if not _is_admin(update):
        linked_name = get_linked_name(update.effective_user.id)
        if linked_name:
            return await show_summary(update, context, linked_name)

    query = " ".join(context.args).strip() if context.args else ""
    if not query:
        await safe_reply_html(
            update,
            t("ask_verification"),
        )
        return NAME
    return await handle_verification(update, context, query)


async def on_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    from cpd.services.storage import get_linked_name
    if not _is_admin(update):
        linked_name = get_linked_name(update.effective_user.id)
        if linked_name:
            return await show_summary(update, context, linked_name)

    return await handle_verification(update, context,
                                     update.effective_message.text or "")


async def handle_verification(update: Update, context: ContextTypes.DEFAULT_TYPE,
                              query: str) -> str:
    """Resolve a query (name, phone, ID, department, etc.) to a participant."""
    from cpd.handlers.common import _cpd
    from cpd.services.search import find_participant_by_secret, search_all_fields

    try:
        data = _cpd(context)
    except Exception:  # noqa: BLE001
        await safe_reply_html(update, t("loading_error"))
        return NAME

    if not query.strip():
        await safe_reply_html(update, t("ask_verification"))
        return NAME

    if _is_admin(update):
        participant, shortlist = search_all_fields(query, data)
    else:
        # Non-admins may only look up their own record using a unique
        # identifier (participant ID or phone number), never by name, so they
        # cannot browse other people's CPD history.
        participant = find_participant_by_secret(data.participants, query)
        shortlist = []

    if participant is None and not shortlist:
        await safe_reply_html(update, t("not_found_verification"))
        return NAME

    if participant is not None:
        if not _is_admin(update):
            from cpd.services.storage import link_account
            link_account(update.effective_user.id, participant.name)
            await safe_reply_html(update,
                                  fmt("account_linked", name=escape(participant.name)))
        return await show_summary(update, context, participant.name)

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


async def on_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    query = update.callback_query
    if query is None:
        return MENU
    await query.answer()
    name = query.data.split("|", 1)[1]

    if not _is_admin(update):
        from cpd.services.storage import link_account
        link_account(update.effective_user.id, name)
        await safe_reply_html(update, fmt("account_linked", name=escape(name)))

    return await show_summary(update, context, name, edit=False)


async def on_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str | None:
    query = update.callback_query
    if query is None:
        return None
    await query.answer()
    action = query.data.split("|", 1)[1]

    if action == "back":
        from cpd.constants import START_OPTIONS
        from cpd.handlers.common import _start_keyboard
        await query.edit_message_text(
            f"<b>{t('welcome')}</b>",
            parse_mode="HTML",
            reply_markup=_start_keyboard(),
        )
        return START_OPTIONS
    return MENU


async def show_certificates(update: Update, context: ContextTypes.DEFAULT_TYPE,
                            name: str, edit: bool = False) -> str:
    from cpd.handlers.common import _cpd

    data = _cpd(context)
    participant = _resolve_for_name(data, name)

    context.user_data["name"] = participant.name
    certificates = data.certificates_for(participant.participant_id,
                                         participant.name, participant.khmer_name)
    text = certificate_report(participant.name, certificates)

    try:
        if edit:
            await update.callback_query.edit_message_text(
                text, parse_mode="HTML", reply_markup=menu_keyboard()
            )
            return MENU
        await update.effective_message.reply_html(
            text, reply_markup=menu_keyboard()
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to send certificates for %r: %r", name, exc)
        await safe_reply_html(update, t("error"))
    return MENU


async def show_summary(update: Update, context: ContextTypes.DEFAULT_TYPE,
                       name: str, edit: bool = False) -> str:
    from cpd.handlers.common import _cpd

    data = _cpd(context)
    participant = _resolve_for_name(data, name)

    context.user_data["name"] = participant.name
    trainings = data.trainings_for(participant.participant_id,
                                   participant.name, participant.khmer_name)
    certificates = data.certificates_for(participant.participant_id,
                                         participant.name, participant.khmer_name)

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
                await update.effective_message.reply_html(section,
                                                          reply_markup=markup)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to send summary for %r: %r", name, exc)
        await safe_reply_html(update, t("error"))
    return MENU
