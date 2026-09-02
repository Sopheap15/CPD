"""The /start entry point and the main-menu callbacks."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from cpd.constants import NAME, REG_IDENTITY, REG_KHMER, START_OPTIONS
from cpd.handlers.admin import auto_link_group
from cpd.handlers.common import _is_admin, _start_keyboard, send_start_message
from cpd.handlers.history import show_summary
from cpd.handlers.pickup import start_pickup
from cpd.handlers.registration import (
    resolve_known_participant,
    show_registration_courses,
)
from cpd.i18n import t
from cpd.services.storage import get_linked_name


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    # /start <cpd_CXXX> inside a group: the admin added the bot to a group via
    # the "Setup group" button — auto-link that group to the course.
    if update.effective_chat.type in ("group", "supergroup") and context.args:
        payload = (context.args[0] or "").strip()
        if payload.startswith("cpd_"):
            return await auto_link_group(update, context, payload[4:])
    await send_start_message(context, update.effective_chat.id)
    return START_OPTIONS


async def on_start_option(update: Update,
                          context: ContextTypes.DEFAULT_TYPE) -> str:
    query = update.callback_query
    if query is None:
        return START_OPTIONS
    await query.answer()
    action = query.data.split("|")[1]
    if action == "back":
        await query.edit_message_text(
            f"<b>{t('welcome')}</b>",
            parse_mode="HTML",
            reply_markup=_start_keyboard(),
        )
        return START_OPTIONS
    if action == "view_cpd":

        last_name = context.user_data.get("last_view_name")
        if last_name:
            context.user_data.pop("last_view_name", None)
            return await show_summary(update, context, last_name, edit=True)

        if not _is_admin(update):
            linked_name = get_linked_name(update.effective_user.id)
            if linked_name:
                return await show_summary(update, context, linked_name, edit=True)
        await query.edit_message_text(t("ask_verification"), parse_mode="HTML")
        return NAME
    if action == "certificate":
        return await start_pickup(update, context)
    elif action == "register":
        # Returning / recognized users go straight to the course list —
        # unless their Khmer name is still unknown, which is asked once.
        known = await resolve_known_participant(update, context)
        if known is not None:
            context.user_data["reg_participant"] = known
            if not (known.khmer_name or "").strip():
                context.user_data["reg_known_pending_khmer"] = True
                await query.edit_message_text(t("reg_ask_khmer_name"),
                                              parse_mode="HTML")
                return REG_KHMER
            return await show_registration_courses(update, context)
        # New user: ask license or name first to identify them.
        await query.edit_message_text(t("reg_ask_identity"), parse_mode="HTML")
        return REG_IDENTITY
    return START_OPTIONS