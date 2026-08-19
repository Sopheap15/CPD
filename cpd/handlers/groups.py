"""Course-group join flow: invite links and admin setup nudges."""

from __future__ import annotations

from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from cpd.config import ADMIN_IDS
from cpd.i18n import fmt, t


async def offer_group_join(context: ContextTypes.DEFAULT_TYPE, chat_id: int,
                           course) -> None:
    """Send the participant an invite link to the course's Telegram group.

    Bots cannot add members to groups, so an invite link is the only way to
    let a participant in. The link is created fresh with
    ``create_chat_invite_link`` when the bot is an admin of the group;
    otherwise the course's ``Link`` column (courses.xlsx) is used as a fallback.
    """
    from cpd.services.course_groups import get_group_chat_id

    group_chat_id = None
    try:
        group_chat_id = get_group_chat_id(course.course_id)
    except Exception:  # noqa: BLE001
        group_chat_id = None

    link = None
    if group_chat_id is not None:
        try:
            invite = await context.bot.create_chat_invite_link(
                group_chat_id,
                name=f"CPD {course.course_id}",
                expire_date=None,
                member_limit=0,
            )
            link = invite.invite_link
        except Exception:  # noqa: BLE001 - bot not admin or group gone
            link = None

    if link is None and course.link:
        link = course.link

    if link:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(t("reg_join_group_button"), url=link)]
        ])
        try:
            await context.bot.send_message(
                chat_id,
                fmt("reg_join_group", link=escape(link)),
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        except Exception:  # noqa: BLE001 - Telegram hiccup
            pass
    elif group_chat_id is not None:
        # Group is linked but the bot isn't its admin -> tell the admins to fix it.
        try:
            await context.bot.send_message(chat_id, t("reg_group_needs_admin"),
                                           parse_mode="HTML")
        except Exception:  # noqa: BLE001
            pass
    else:
        try:
            await context.bot.send_message(chat_id, t("reg_no_group"),
                                           parse_mode="HTML")
        except Exception:  # noqa: BLE001
            pass
        await ask_admin_to_setup_group(context, chat_id, course)


async def ask_admin_to_setup_group(context: ContextTypes.DEFAULT_TYPE,
                                   requester_chat_id: int, course) -> None:
    """Notify every admin that a course group is missing, with a one-tap
    deep-link button that links a group (as admin) to the course."""
    if not ADMIN_IDS:
        return
    try:
        me = await context.bot.get_me()
        bot_username = me.username or "UNKNOWN_BOT"
    except Exception:  # noqa: BLE001
        return
    url = (f"https://t.me/{bot_username}?startgroup=cpd_{course.course_id}"
           f"&admin=change_info+invite_users")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("admin_setup_button"), url=url)],
        [InlineKeyboardButton(t("admin_setup_new_group"), url="tg://new/group")],
    ])
    text = fmt("admin_setup_needed", course=escape(course.title),
               course_id=escape(course.course_id))
    for admin_id in ADMIN_IDS:
        if admin_id == requester_chat_id:
            continue
        try:
            await context.bot.send_message(admin_id, text, parse_mode="HTML",
                                           reply_markup=keyboard)
        except Exception:  # noqa: BLE001 - admin may not have started the bot
            pass
