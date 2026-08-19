"""Telegram bot: receives a participant name and shows CPD history."""

from __future__ import annotations

import logging
import time
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
START_OPTIONS = "START_OPTIONS"
NAME = "NAME"
MENU = "MENU"
REG_IDENTITY = "REG_IDENTITY"
REG_COURSE = "REG_COURSE"
REG_LICENSE = "REG_LICENSE"
REG_NAME = "REG_NAME"
REG_PHONE = "REG_PHONE"
REG_LOCATION = "REG_LOCATION"
REG_PAYMENT = "REG_PAYMENT"

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



async def _on_start_option(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
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
        from cpd.storage import get_linked_name
        if not _is_admin(update):
            linked_name = get_linked_name(update.effective_user.id)
            if linked_name:
                return await _show_summary(update, context, linked_name, edit=True)
            await query.edit_message_text(t("ask_verification"), parse_mode="HTML")
        else:
            await query.edit_message_text(t("ask_admin_view"), parse_mode="HTML")
        return NAME
    elif action == "register":
        # Returning / recognized users go straight to the course list.
        known = await _resolve_known_participant(update, context)
        if known is not None:
            context.user_data["reg_participant"] = known
            return await _show_registration_courses(update, context)
        # New user: ask license or name first to identify them.
        await query.edit_message_text(t("reg_ask_identity"), parse_mode="HTML")
        return REG_IDENTITY
    return START_OPTIONS

# ------------------------------------------------------------ registration
async def _resolve_known_participant(update: Update,
                                     context: ContextTypes.DEFAULT_TYPE):
    """Return a participant this user is already known as, or None.

    Checks (in order): Telegram-linked account, then any previous in-bot
    registration. This lets returning users skip all questions.
    """
    from cpd.storage import get_linked_name
    data = _cpd(context)
    linked_name = get_linked_name(update.effective_user.id)
    if linked_name:
        participant = exact_participant(data.participants, linked_name) or \
            next((p for p in data.participants if p.name == linked_name), None)
        if participant is not None and (participant.participant_id or participant.phone):
            return participant

    from cpd.registrations import latest_registration_for_user
    from cpd.data_loader import Participant
    prior = latest_registration_for_user(update.effective_user.id)
    if prior is not None:
        return Participant(
            participant_id=prior.get("participant_id", ""),
            name=prior.get("name", ""),
            phone=prior.get("phone", ""),
            department=prior.get("location", ""),
        )
    return None


def _course_buttons(courses) -> InlineKeyboardMarkup:
    """Inline buttons for every open course."""
    rows = [
        [InlineKeyboardButton(
            f"{c.title} — {c.date}" if c.date else c.title,
            callback_data=f"reg|{c.course_id}",
        )]
        for c in courses
    ]
    rows.append([InlineKeyboardButton("⬅️ ត្រឡប់ក្រោយ (Back)", callback_data="start|back")])
    return InlineKeyboardMarkup(rows)


def _open_courses(data) -> list:
    return [
        c for c in data.courses
        if c.status.strip().lower() not in ("done", "completed", "ចប់")
    ]


async def _show_registration_courses(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    query = update.callback_query
    data = _cpd(context)
    courses = _open_courses(data)
    if not courses:
        text = "គ្មានវគ្គបណ្តុះបណ្តាលសម្រាប់ការចុះឈ្មោះទេនៅពេលនេះ។ (No courses available for registration at this time.)"
        await query.edit_message_text(text, parse_mode="HTML",
                                      reply_markup=InlineKeyboardMarkup([
                                          [InlineKeyboardButton("⬅️ ត្រឡប់ក្រោយ (Back)", callback_data="start|back")]
                                      ]))
        return START_OPTIONS
    text = "<b>📚 សូមជ្រើសរើសវគ្គបណ្តុះបណ្តាល (Choose a course):</b>\n\n"
    for c in courses:
        text += f"• <b>{escape(c.title)}</b>\n"
        if c.date:
            text += f"  🗓️ កាលបរិច្ឆេទ (Date): {escape(c.date)}\n"
        if c.cpd_points:
            text += f"  ⭐ ពិន្ទុ CPD (CPD Points): {escape(c.cpd_points)}\n"
        if c.fee:
            fee = f"{c.fee:.2f}".rstrip("0").rstrip(".")
            text += f"  💵 ថ្លៃ (Fee): ${fee}\n"
    text += NL + NL + t("further_info")
    await query.edit_message_text(text, parse_mode="HTML",
                                  disable_web_page_preview=True,
                                  reply_markup=_course_buttons(courses))
    return REG_COURSE


async def _on_reg_identity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """User typed a license number or full name to identify themselves."""
    from cpd.registrations import registration_by_name
    from cpd.search import find_participant_by_secret, find_best
    text = (update.effective_message.text or "").strip()
    if not text:
        await safe_reply_html(update, t("reg_ask_identity"))
        return REG_IDENTITY
    data = _cpd(context)
    known = find_participant_by_secret(data.participants, text)
    if known is None:
        known = exact_participant(data.participants, text) or \
            find_best(data.participants, text)
    # Returning participant recognised by their previous in-bot registration.
    prior = None
    if known is None:
        prior = registration_by_name(update.effective_user.id, text)
        if prior is not None:
            from cpd.data_loader import Participant
            known = Participant(
                participant_id=prior.get("participant_id", ""),
                name=prior.get("name", ""),
                phone=prior.get("phone", ""),
                department=prior.get("location", ""),
            )
    if known is not None:
        context.user_data["reg_participant"] = known
        context.user_data["reg_license"] = known.participant_id or ""
        context.user_data["reg_name"] = known.name or ""
        context.user_data["reg_phone"] = known.phone or ""
        context.user_data["reg_location"] = known.department or ""
        await _send_courses_as_message(update, context)
        return REG_COURSE
    # Not recognized -> new user. Capture license AND name (order depends on
    # what they typed first), then phone + location.
    if any(ch.isdigit() for ch in text):
        context.user_data["reg_license"] = text
        if context.user_data.get("reg_name"):
            await safe_reply_html(update, t("reg_ask_phone"))
            return REG_PHONE
        await safe_reply_html(update, t("reg_ask_name"))
        return REG_NAME
    # Looks like a name -> ask for the license number next.
    context.user_data["reg_name"] = text
    await safe_reply_html(update, t("reg_ask_license"))
    return REG_LICENSE


async def _send_courses_as_message(update: Update,
                                   context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the course list as a fresh message (used after text identification)."""
    data = _cpd(context)
    courses = _open_courses(data)
    text = "<b>📚 សូមជ្រើសរើសវគ្គបណ្តុះបណ្តាល (Choose a course):</b>\n\n"
    for c in courses:
        text += f"• <b>{escape(c.title)}</b>\n"
        if c.date:
            text += f"  🗓️ កាលបរិច្ឆេទ (Date): {escape(c.date)}\n"
        if c.cpd_points:
            text += f"  ⭐ ពិន្ទុ CPD (CPD Points): {escape(c.cpd_points)}\n"
        if c.fee:
            fee = f"{c.fee:.2f}".rstrip("0").rstrip(".")
            text += f"  💵 ថ្លៃ (Fee): ${fee}\n"
    text += NL + NL + t("further_info")
    await update.effective_message.reply_html(
        text,
        disable_web_page_preview=True,
        reply_markup=_course_buttons(courses),
    )


async def _on_reg_course(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    query = update.callback_query
    if query is None:
        return REG_COURSE
    await query.answer()
    course_id = query.data.split("|")[1]
    context.user_data["reg_course_id"] = course_id
    data = _cpd(context)
    course = next((c for c in data.courses if c.course_id == course_id), None)
    if course is None:
        await query.edit_message_text(t("reg_pick_course"), parse_mode="HTML")
        return REG_COURSE
    context.user_data["reg_course"] = course

    # The participant was identified earlier (telegram link / prior registration
    # / license+name). If not, fall back to asking for details.
    participant = context.user_data.get("reg_participant")
    if participant is None:
        await query.edit_message_text(t("reg_ask_identity"), parse_mode="HTML")
        return REG_IDENTITY

    # Already registered for this course -> no payment, just re-offer the group.
    from cpd.registrations import has_duplicate
    if has_duplicate(update.effective_user.id, course.course_id):
        await safe_reply_html(update, t("reg_already"))
        await _offer_group_join(context, update.effective_chat.id, course)
        _clear_registration_state(context)
        await _send_start_message(context, update.effective_chat.id)
        return START_OPTIONS

    return await _start_payment(update, context, course, participant)


async def _start_payment(update: Update, context: ContextTypes.DEFAULT_TYPE,
                         course, participant) -> str:
    """Create the KHQR for the course fee and show it to the participant.

    Returns ``REG_PAYMENT`` so the bot waits for the payment callback, or
    registers the participant directly when no payment is required / not
    configured.
    """
    from cpd.config import BAKONG_CURRENCY
    from cpd.payments import create_payment
    from cpd.registrations import append_registration

    chat_id = update.effective_chat.id
    pending = create_payment(
        chat_id,
        update.effective_user.id,
        course,
        participant,
        user_data={
            "participant": {
                "name": participant.name,
                "participant_id": participant.participant_id,
                "phone": participant.phone,
                "location": participant.department,
            },
            "course": {
                "course_id": course.course_id,
                "title": course.title,
                "date": course.date,
                "cpd_points": course.cpd_points,
                "fee": course.fee,
                "link": course.link,
            },
        },
    )

    if pending is None:
        # No fee or Bakong not configured -> register immediately.
        return await _complete_registration(update, context, participant)

    # Keep a "pending payment" row so the admin can see outstanding fees.
    append_registration({
        "telegram_id": update.effective_user.id,
        "name": participant.name,
        "participant_id": participant.participant_id,
        "phone": participant.phone,
        "location": participant.department,
        "course_id": course.course_id,
        "course_title": course.title,
        "course_date": course.date,
        "cpd_points": course.cpd_points,
        "fee": course.fee,
        "currency": BAKONG_CURRENCY,
        "bill_number": pending.bill_number,
        "qr_md5": pending.md5,
        "payment_status": "Pending",
        "status": "Pending payment",
    })

    amount = f"{pending.amount:.2f}".rstrip("0").rstrip(".")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("pay_check_button"), callback_data="pay|check")],
        [InlineKeyboardButton(t("pay_cancel_button"), callback_data="pay|cancel")],
    ])
    caption = fmt("pay_intro", course=escape(course.title),
                  amount=amount, currency=BAKONG_CURRENCY)
    if pending.user_data.get("can_verify", True):
        caption += "\n\n" + t("pay_intro_auto")
    else:
        caption += "\n\n" + t("pay_manual_mode")
    try:
        with open(pending.user_data["qr_image_path"], "rb") as fh:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=fh,
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
    except Exception:  # noqa: BLE001 - QR image failed; fall back to text
        await safe_reply_html(update, caption, reply_markup=keyboard)
    return REG_PAYMENT


async def _on_pay_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Callback 'pay|check': confirm payment and finish registration."""
    query = update.callback_query
    if query is None:
        return REG_PAYMENT
    await query.answer()
    chat_id = update.effective_chat.id

    from cpd.payments import check_payment, drop_payment, get_pending, payment_expired
    pending = get_pending(chat_id)
    if pending is None:
        await safe_reply_html(update, t("pay_expired"))
        _clear_registration_state(context)
        return START_OPTIONS
    if payment_expired(chat_id):
        drop_payment(chat_id)
        await safe_reply_html(update, t("pay_expired"))
        _clear_registration_state(context)
        return START_OPTIONS

    # Without a Bakong token we can't poll the transaction, so a manual
    # "I have paid" is treated as confirmation and the admin is notified.
    if check_payment(chat_id) or not pending.user_data.get("can_verify", True):
        await _finalize_paid_registration(context, pending,
                                          verified=check_payment(chat_id))
        _clear_registration_state(context)
        return START_OPTIONS
    await safe_reply_html(update, t("pay_unpaid"))
    return REG_PAYMENT


async def _on_pay_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Callback 'pay|cancel': drop the pending payment and the registration."""
    query = update.callback_query
    if query is None:
        return REG_PAYMENT
    await query.answer()
    chat_id = update.effective_chat.id
    from cpd.payments import drop_payment
    drop_payment(chat_id)
    _clear_registration_state(context)
    await query.edit_message_text(t("cancel"), parse_mode="HTML")
    await _send_start_message(context, chat_id)
    return START_OPTIONS


async def _finalize_paid_registration(context: ContextTypes.DEFAULT_TYPE,
                                      pending, verified: bool = True) -> None:
    """Complete a registration after payment confirmation.

    ``verified=True`` means Bakong confirmed the transaction (or auto-verification
    is configured). ``verified=False`` is a manual "I have paid" tap when the
    developer token is still missing — the registration is saved as Unverified.
    """
    from cpd.config import BAKONG_CURRENCY
    from cpd.data_loader import Course, Participant
    from cpd.payments import drop_payment
    from cpd.registrations import mark_paid

    p = pending.user_data.get("participant", {})
    c = pending.user_data.get("course", {})
    participant = Participant(
        participant_id=p.get("participant_id", ""),
        name=p.get("name", ""),
        phone=p.get("phone", ""),
        department=p.get("location", ""),
    )
    course = Course(
        course_id=c.get("course_id", pending.course_id),
        title=c.get("title", pending.course_title),
        date=c.get("date", ""),
        cpd_points=c.get("cpd_points", ""),
        link=c.get("link", ""),
        fee=c.get("fee", pending.amount),
    )
    chat_id = pending.chat_id
    amount = f"{pending.amount:.2f}".rstrip("0").rstrip(".")

    # The "Pending payment" row was already written when the QR was created;
    # flip it to paid now.
    mark_paid(pending.bill_number,
              payment_status="Paid" if verified else "Unverified")
    drop_payment(chat_id)

    from cpd.storage import get_linked_name, link_account
    if participant.name and get_linked_name(pending.telegram_id) is None:
        link_account(pending.telegram_id, participant.name)

    try:
        await context.bot.send_message(
            chat_id,
            fmt("pay_success" if verified else "pay_success_pending",
                amount=amount, currency=BAKONG_CURRENCY,
                course=escape(course.title)),
            parse_mode="HTML",
        )
        payment_line = fmt(
            "payment_line_ok" if verified else "payment_line_pending",
            amount=amount, currency=BAKONG_CURRENCY)
        await context.bot.send_message(
            chat_id,
            fmt("reg_confirm_paid",
                course=escape(course.title),
                name=escape(participant.name or ""),
                license=escape(participant.participant_id or "-"),
                phone=escape(participant.phone or "-"),
                location=escape(participant.department or "-"),
                telegram_id=pending.telegram_id,
                date=time.strftime("%Y-%m-%d %H:%M"),
                payment_line=payment_line),
            parse_mode="HTML",
        )
    except Exception:  # noqa: BLE001 - Telegram hiccup; non-fatal
        pass

    await _offer_group_join(context, chat_id, course)
    await _send_start_message(context, chat_id)


async def _on_reg_license(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    license_val = (update.effective_message.text or "").strip()
    if not license_val:
        await safe_reply_html(update, t("reg_ask_license"))
        return REG_LICENSE
    context.user_data["reg_license"] = license_val

    # If this license already exists in the records, reuse that person's
    # name/phone so they don't have to re-enter anything.
    from cpd.search import find_participant_by_secret
    data = _cpd(context)
    known = find_participant_by_secret(data.participants, license_val)
    if known is not None:
        context.user_data["reg_participant"] = known
        context.user_data["reg_name"] = known.name or ""
        context.user_data["reg_phone"] = known.phone or ""
        context.user_data["reg_location"] = known.department or ""
        await _send_courses_as_message(update, context)
        return REG_COURSE

    # Name already given at the identity step -> skip straight to phone.
    if context.user_data.get("reg_name"):
        await safe_reply_html(update, t("reg_ask_phone"))
        return REG_PHONE
    await safe_reply_html(update, t("reg_ask_name"))
    return REG_NAME


async def _on_reg_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    name = (update.effective_message.text or "").strip()
    if not name:
        await safe_reply_html(update, t("reg_ask_name"))
        return REG_NAME
    context.user_data["reg_name"] = name
    await safe_reply_html(update, t("reg_ask_phone"))
    return REG_PHONE


async def _on_reg_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    phone = (update.effective_message.text or "").strip()
    if not phone:
        await safe_reply_html(update, t("reg_ask_phone"))
        return REG_PHONE
    context.user_data["reg_phone"] = phone
    await safe_reply_html(update, t("reg_ask_location"))
    return REG_LOCATION


async def _on_reg_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    location = (update.effective_message.text or "").strip()
    if not location:
        await safe_reply_html(update, t("reg_ask_location"))
        return REG_LOCATION
    context.user_data["reg_location"] = location

    from cpd.data_loader import Participant
    participant = Participant(
        participant_id=context.user_data.get("reg_license", ""),
        name=context.user_data.get("reg_name", ""),
        phone=context.user_data.get("reg_phone", ""),
        department=location,
    )
    context.user_data["reg_participant"] = participant
    await _send_courses_as_message(update, context)
    return REG_COURSE


async def _complete_registration(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                 participant) -> str:
    course = context.user_data.get("reg_course")
    if course is None:
        await safe_reply_html(update, t("reg_pick_course"))
        return REG_COURSE
    from cpd.registrations import append_registration
    chat_id = update.effective_chat.id

    append_registration({
        "telegram_id": update.effective_user.id,
        "name": participant.name,
        "participant_id": participant.participant_id,
        "phone": participant.phone,
        "location": participant.department,
        "course_id": course.course_id,
        "course_title": course.title,
        "course_date": course.date,
        "cpd_points": course.cpd_points,
        "fee": course.fee,
        "status": "Registered",
    })

    from cpd.storage import get_linked_name, link_account
    if participant.name and get_linked_name(update.effective_user.id) is None:
        link_account(update.effective_user.id, participant.name)

    msg = fmt("reg_confirm_new" if participant.name else "reg_confirm_old",
              course=escape(course.title),
              name=escape(participant.name or ""),
              license=escape(participant.participant_id or "-"),
              phone=escape(participant.phone or "-"),
              location=escape(participant.department or "-"),
              telegram_id=update.effective_user.id,
              date=time.strftime("%Y-%m-%d %H:%M"))
    await safe_reply_html(update, msg)

    await _offer_group_join(context, chat_id, course)

    _clear_registration_state(context)
    await _send_start_message(context, chat_id)
    return START_OPTIONS


async def _offer_group_join(context: ContextTypes.DEFAULT_TYPE, chat_id: int,
                            course) -> None:
    """Send the participant an invite link to the course's Telegram group.

    Bots cannot add members to groups, so an invite link is the only way to
    let a participant in. The link is created fresh with ``create_chat_invite_link``
    when the bot is an admin of the group; otherwise the course's ``Link``
    column (courses.xlsx) is used as a fallback.
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    group_chat_id = None
    from cpd.course_groups import get_group_chat_id
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
        await _ask_admin_to_setup_group(context, chat_id, course)


async def _ask_admin_to_setup_group(context: ContextTypes.DEFAULT_TYPE,
                                    requester_chat_id: int, course) -> None:
    """Notify every admin that a course group is missing, with a one-tap
    deep-link button that links a group (as admin) to the course."""
    from cpd.config import ADMIN_IDS
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


def _clear_registration_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in ("reg_course_id", "reg_course", "reg_license",
                "reg_name", "reg_phone", "reg_location", "reg_participant"):
        context.user_data.pop(key, None)

# ----------------------------------------------------------------- commands
def _start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 ចុះឈ្មោះវគ្គបណ្តុះបណ្តាល (Register for Course)", callback_data="start|register")],
        [InlineKeyboardButton("📊 មើលប្រវត្តិ CPD (View CPD History)", callback_data="start|view_cpd")]
    ])


async def _send_start_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int,
                              extra: str = "") -> None:
    """Send the bot icon (if any) followed by the welcome + commands message."""
    from cpd.config import BOT_ICON
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


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    # /start <cpd_CXXX> inside a group: the admin added the bot to a group via
    # the "Setup group" button — auto-link that group to the course.
    if update.effective_chat.type in ("group", "supergroup") and context.args:
        payload = (context.args[0] or "").strip()
        if payload.startswith("cpd_"):
            return await _auto_link_group(update, context, payload[4:])
    if _is_admin(update):
        # Admins: ask which participant they want to view (no linked-account shortcut).
        await _send_start_message(context, update.effective_chat.id, extra=t("ask_admin_view"))
        return NAME
    await _send_start_message(context, update.effective_chat.id)
    return START_OPTIONS


async def cmd_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    from cpd.storage import get_linked_name
    if not _is_admin(update):
        linked_name = get_linked_name(update.effective_user.id)
        if linked_name:
            return await _show_summary(update, context, linked_name)

    query = " ".join(context.args).strip() if context.args else ""
    if not query:
        await safe_reply_html(update, t("ask_admin_view") if _is_admin(update) else t("ask_verification"))
        return NAME
    return await _handle_verification(update, context, query)


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    context.user_data.pop("name", None)
    await safe_reply_html(update, t("cancel"))
    return ConversationHandler.END


async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the user their own Telegram ID."""
    tid = update.effective_user.id
    await safe_reply_html(update, fmt("your_telegram_id", tid=tid))


async def cmd_unlink(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Unlink the current Telegram account from its participant record."""
    from cpd.storage import get_linked_name, unlink_account
    name = get_linked_name(update.effective_user.id)
    if not name:
        await safe_reply_html(update, t("not_linked"))
        return ConversationHandler.END
    unlink_account(update.effective_user.id)
    context.user_data.pop("name", None)
    await safe_reply_html(update, t("account_unlinked"))
    return ConversationHandler.END


# ----------------------------------------------------------- admin commands
def _is_admin(update: Update) -> bool:
    from cpd.config import ADMIN_IDS
    return update.effective_user.id in ADMIN_IDS


async def cmd_admin_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: list all linked accounts."""
    if not _is_admin(update):
        await safe_reply_html(update, t("admin_only"))
        return
    from cpd.storage import list_all_links
    links = list_all_links()
    if not links:
        await safe_reply_html(update, "No accounts linked yet.")
        return
    lines = ["<b>🔗 Linked accounts:</b>"]
    for tid, name in sorted(links.items(), key=lambda x: x[1]):
        lines.append(f"• <code>{tid}</code> → {escape(name)}")
    await safe_reply_html(update, "\n".join(lines))


async def cmd_admin_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: /admin_link <TelegramID> <Participant Name>"""
    if not _is_admin(update):
        await safe_reply_html(update, t("admin_only"))
        return
    args = context.args or []
    if len(args) < 2 or not args[0].isdigit():
        await safe_reply_html(update,
            "Usage: /admin_link &lt;TelegramID&gt; &lt;Full Name&gt;\n"
            "Example: /admin_link 123456789 KY Kimhuy")
        return
    tid = int(args[0])
    name = " ".join(args[1:])
    from cpd.storage import link_account
    link_account(tid, name)
    await safe_reply_html(update,
        f"✅ Linked <code>{tid}</code> → <b>{escape(name)}</b>")


async def cmd_admin_unlink(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: /admin_unlink <TelegramID or Name>"""
    if not _is_admin(update):
        await safe_reply_html(update, t("admin_only"))
        return
    args = context.args or []
    if not args:
        await safe_reply_html(update,
            "Usage: /admin_unlink &lt;TelegramID or Full Name&gt;\n"
            "Example: /admin_unlink 123456789\n"
            "Example: /admin_unlink KY Kimhuy")
        return
    from cpd.storage import admin_unlink_by_name, unlink_account
    query = " ".join(args)
    if query.isdigit():
        unlink_account(int(query))
        await safe_reply_html(update, f"✅ Unlinked Telegram ID <code>{query}</code>")
    else:
        found = admin_unlink_by_name(query)
        if found:
            await safe_reply_html(update, f"✅ Unlinked account for <b>{escape(query)}</b>")
        else:
            await safe_reply_html(update,
                f"❌ No linked account found for <b>{escape(query)}</b>")


async def cmd_admin_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Admin: /admin_view <Participant Name> — view any participant's CPD history."""
    if not _is_admin(update):
        await safe_reply_html(update, t("admin_only"))
        return ConversationHandler.END
    args = context.args or []
    if not args:
        await safe_reply_html(update,
            "Usage: /admin_view &lt;Full Name&gt;\n"
            "Example: /admin_view KY Kimhuy")
        return ConversationHandler.END
    name = " ".join(args)
    return await _show_summary(update, context, name)


async def _auto_link_group(update: Update, context: ContextTypes.DEFAULT_TYPE,
                           course_id: str) -> str:
    """Auto-link the current group to a course when the bot is added via the
    'Setup group' deep link (https://t.me/<bot>?startgroup=cpd_<CourseID>).
    Only the bot's admin (ADMIN_IDS) is allowed to do this."""
    if not _is_admin(update):
        await safe_reply_html(update, t("admin_only"))
        return ConversationHandler.END
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        return ConversationHandler.END
    data = _cpd(context)
    course = next((c for c in data.courses if c.course_id == course_id), None)
    if course is None:
        await safe_reply_html(update,
                              fmt("admin_group_unknown_course", course_id=escape(course_id)))
        return ConversationHandler.END
    from cpd.course_groups import set_group_chat_id
    set_group_chat_id(course_id, chat.id)
    # Rename the group to "Date - Title" so participants see the right name.
    title = f"{course.date} - {course.title}" if course.date else course.title
    is_admin = False
    try:
        me = await context.bot.get_me()
        member = await context.bot.get_chat_member(chat.id, me.id)
        is_admin = member.status in ("administrator", "creator")
        if is_admin:
            await context.bot.set_chat_title(chat.id, title)
    except Exception:  # noqa: BLE001 - bot may not be admin yet
        is_admin = False
    if is_admin:
        await safe_reply_html(update,
                              fmt("admin_group_ok", course=escape(course.title),
                                  course_id=escape(course_id)))
    else:
        await safe_reply_html(update, t("admin_group_make_admin"))
    return ConversationHandler.END


async def cmd_admin_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: /admin_group <Course ID> — link the current group to a course."""
    if not _is_admin(update):
        await safe_reply_html(update, t("admin_only"))
        return
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await safe_reply_html(update, t("admin_group_not_group"))
        return
    args = context.args or []
    if len(args) < 1:
        await safe_reply_html(update, t("admin_group_usage"))
        return
    course_id = args[0].strip()
    data = _cpd(context)
    course = next((c for c in data.courses if c.course_id == course_id), None)
    if course is None:
        await safe_reply_html(update,
                              fmt("admin_group_unknown_course", course_id=escape(course_id)))
        return
    from cpd.course_groups import set_group_chat_id
    set_group_chat_id(course_id, chat.id)
    await safe_reply_html(update,
                          fmt("admin_group_ok", course=escape(course.title),
                              course_id=escape(course_id)))


async def cmd_admin_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: /admin_setup — one-tap buttons that link a group to each open course.

    Each button opens Telegram's 'add bot to a group' dialog and requests admin
    rights (change_info + invite_users) so the bot can rename the group and
    create invite links. When the bot is added that way, it auto-links the
    group to the course and renames the group to 'Date - Title'.
    """
    if not _is_admin(update):
        await safe_reply_html(update, t("admin_only"))
        return
    try:
        me = await context.bot.get_me()
        bot_username = me.username or "UNKNOWN_BOT"
    except Exception:  # noqa: BLE001
        await safe_reply_html(update, t("admin_group_make_admin"))
        return
    data = _cpd(context)
    courses = _open_courses(data)
    if not courses:
        await safe_reply_html(update, "No open courses to set up.")
        return
    from cpd.course_groups import get_group_chat_id
    lines = ["<b>🛠 Setup course groups</b>\n"
             "Tap a button, choose the course's group (or create one in "
             "Telegram first), and the bot will link + rename it automatically "
             "with admin rights.\n"]
    rows = []
    for c in courses:
        linked = get_group_chat_id(c.course_id) is not None
        label = (f"✅ {c.course_id}" if linked else f"🔗 {c.course_id}")
        lines.append(f"{label} — <b>{escape(c.title)}</b>"
                     f"{f' ({escape(c.date)})' if c.date else ''}")
        rows.append([InlineKeyboardButton(
            label,
            url=f"https://t.me/{bot_username}?startgroup=cpd_{c.course_id}"
                f"&admin=change_info+invite_users",
        )])
    # One-tap "create a new group" so the admin can make the group right here.
    rows.append([InlineKeyboardButton("➕ បង្កើតក្រុមថ្មី (Create a new group)",
                                      url="tg://new/group")])
    await safe_reply_html(update, "\n".join(lines),
                          reply_markup=InlineKeyboardMarkup(rows))


async def cmd_admin_group_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: /admin_group_clear <Course ID> — unlink a course's group."""
    if not _is_admin(update):
        await safe_reply_html(update, t("admin_only"))
        return
    args = context.args or []
    if len(args) < 1:
        await safe_reply_html(update,
            "Usage: /admin_group_clear &lt;Course ID&gt;\n"
            "Example: /admin_group_clear C002")
        return
    course_id = args[0].strip()
    from cpd.course_groups import clear_group_chat_id
    clear_group_chat_id(course_id)
    await safe_reply_html(update, f"✅ Unlinked group for course <b>{escape(course_id)}</b>")


async def cmd_admin_regs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: /admin_regs — list all in-bot registrations (incl. pending fees)."""
    if not _is_admin(update):
        await safe_reply_html(update, t("admin_only"))
        return
    from cpd.registrations import load_registrations
    rows = load_registrations()
    if not rows:
        await safe_reply_html(update, "No registrations yet.")
        return
    lines = [f"<b>📝 Registrations ({len(rows)}):</b>"]
    for r in reversed(rows):
        name = escape(r.get("name", "") or "-")
        course = escape(r.get("course_title", "") or r.get("course_id", "") or "-")
        pay = escape(r.get("payment_status", "") or r.get("status", "") or "-")
        when = escape(r.get("registered_at", "") or "")
        lines.append(f"• <b>{course}</b> — {name} [{pay}]{f' ({when})' if when else ''}")
    await safe_reply_html(update, "\n".join(lines[:50]))


async def cmd_admin_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: /admin_confirm <bill_number> — mark a manual payment as Paid."""
    if not _is_admin(update):
        await safe_reply_html(update, t("admin_only"))
        return
    args = context.args or []
    if len(args) < 1:
        await safe_reply_html(update,
            "Usage: /admin_confirm &lt;bill_number&gt;\n"
            "Get the bill number from /admin_regs.")
        return
    bill = args[0].strip()
    from cpd.registrations import mark_paid
    if mark_paid(bill, payment_status="Paid"):
        await safe_reply_html(update,
            f"✅ Payment <code>{escape(bill)}</code> marked as <b>Paid</b>.")
    else:
        await safe_reply_html(update,
            f"❌ No registration found with bill number <code>{escape(bill)}</code>.")


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: /admin — show the admin command menu."""
    if not _is_admin(update):
        await safe_reply_html(update, t("admin_only"))
        return
    await safe_reply_html(update, t("admin_help"))


async def cmd_admin_groups(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: /admin_groups — list course ↔ group chat IDs."""
    if not _is_admin(update):
        await safe_reply_html(update, t("admin_only"))
        return
    from cpd.course_groups import all_group_mappings
    mapping = all_group_mappings()
    if not mapping:
        await safe_reply_html(update, "No course groups linked yet. Use /admin_setup.")
        return
    data = _cpd(context)
    lines = [fmt("admin_groups_title", count=len(mapping))]
    for course_id in sorted(mapping):
        chat_id = mapping[course_id]
        course = next((c for c in data.courses if c.course_id == course_id), None)
        title = escape(course.title) if course else escape(course_id)
        lines.append(f"• <b>{title}</b> — chat <code>{chat_id}</code>")
    await safe_reply_html(update, "\n".join(lines))


async def cmd_admin_group_rename(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: /admin_group_rename <Course ID> <new title> — rename a course group.

    The bot must be an administrator of the group with "change group info"
    rights (as granted by /admin_setup) to rename it.
    """
    if not _is_admin(update):
        await safe_reply_html(update, t("admin_only"))
        return
    args = context.args or []
    if len(args) < 2:
        await safe_reply_html(update, t("admin_group_rename_usage"))
        return
    course_id = args[0].strip()
    title = " ".join(args[1:]).strip()
    from cpd.course_groups import get_group_chat_id
    chat_id = get_group_chat_id(course_id)
    if chat_id is None:
        await safe_reply_html(update, fmt("admin_kick_nogroup", course=escape(course_id)))
        return
    try:
        await context.bot.set_chat_title(chat_id, title)
    except Exception as exc:  # noqa: BLE001 - Telegram error (not admin, etc.)
        await safe_reply_html(update,
            f"❌ Could not rename: {escape(str(exc)[:200])}")
        return
    await safe_reply_html(update, fmt("admin_group_rename_ok", title=escape(title)))


async def cmd_admin_reg_del(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: /admin_reg_del <telegram_id> <course_id> — delete one registration."""
    if not _is_admin(update):
        await safe_reply_html(update, t("admin_only"))
        return
    args = context.args or []
    if len(args) < 2:
        await safe_reply_html(update, t("admin_reg_del_usage"))
        return
    tid = args[0].strip()
    course_id = args[1].strip()
    from cpd.registrations import delete_registration
    if delete_registration(tid, course_id):
        await safe_reply_html(update,
            fmt("admin_reg_del_ok", tid=escape(tid), course=escape(course_id)))
    else:
        await safe_reply_html(update,
            fmt("admin_reg_del_notfound", tid=escape(tid), course=escape(course_id)))


async def cmd_admin_reg_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: /admin_reg_clear [yes] — delete all in-bot registrations."""
    if not _is_admin(update):
        await safe_reply_html(update, t("admin_only"))
        return
    if not (context.args and context.args[0].strip().lower() == "yes"):
        await safe_reply_html(update, t("admin_reg_clear_usage"))
        return
    from cpd.registrations import clear_registrations
    count = clear_registrations()
    await safe_reply_html(update, fmt("admin_reg_clear_ok", count=count))


async def cmd_admin_kick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: /admin_kick <Course ID> <telegram_id> — remove a member from a group.

    The bot must be an administrator of the course group with the "Ban users"
    right (granted when the group is added via /admin_setup) to remove someone.
    """
    if not _is_admin(update):
        await safe_reply_html(update, t("admin_only"))
        return
    args = context.args or []
    if len(args) < 2:
        await safe_reply_html(update, t("admin_kick_usage"))
        return
    course_id = args[0].strip()
    tid = args[1].strip()
    if not tid.lstrip("-").isdigit():
        await safe_reply_html(update, t("admin_kick_usage"))
        return
    from cpd.course_groups import get_group_chat_id
    chat_id = get_group_chat_id(course_id)
    if chat_id is None:
        await safe_reply_html(update, fmt("admin_kick_nogroup", course=escape(course_id)))
        return
    try:
        # Ban, then immediately unban so the user is removed (not blocked).
        await context.bot.ban_chat_member(chat_id, int(tid))
        await context.bot.unban_chat_member(chat_id, int(tid))
    except Exception as exc:  # noqa: BLE001 - Telegram error (not admin, etc.)
        await safe_reply_html(update,
            f"❌ Could not remove member: {escape(str(exc)[:200])}")
        return
    await safe_reply_html(update, fmt("admin_kick_ok", tid=escape(tid),
                                      course=escape(course_id)))


# ------------------------------------------------------------- name lookup
async def on_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    from cpd.storage import get_linked_name
    if not _is_admin(update):
        linked_name = get_linked_name(update.effective_user.id)
        if linked_name:
            return await _show_summary(update, context, linked_name)

    return await _handle_verification(update, context, update.effective_message.text or "")


async def _handle_verification(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str) -> str:
    """Resolve a query (name, phone, ID, department, etc.) to a participant."""
    try:
        data = _cpd(context)
    except Exception:  # noqa: BLE001
        await safe_reply_html(update, t("loading_error"))
        return NAME

    if not query.strip():
        await safe_reply_html(update, t("ask_verification"))
        return NAME

    from cpd.search import find_participant_by_secret, search_all_fields
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
            from cpd.storage import link_account
            link_account(update.effective_user.id, participant.name)
            await safe_reply_html(update, fmt("account_linked", name=escape(participant.name)))
        return await _show_summary(update, context, participant.name)

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
    
    if not _is_admin(update):
        from cpd.storage import link_account
        link_account(update.effective_user.id, name)
        await safe_reply_html(update, fmt("account_linked", name=escape(name)))
    
    return await _show_summary(update, context, name, edit=False)


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
        from cpd.storage import unlink_account
        unlink_account(update.effective_user.id)
        context.user_data.pop("name", None)
        await query.edit_message_text(t("ask_verification"), parse_mode="HTML")
        return NAME
    elif action == "done":
        try:
            await query.message.delete()
        except Exception:
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


async def _register_commands(app: Application) -> None:
    """Publish the bot's command menu (the / button in Telegram chats)."""
    from telegram import BotCommand
    commands = [
        BotCommand("start", "Start / restart the bot"),
        BotCommand("view", "View your CPD history"),
        BotCommand("myid", "Show your Telegram ID"),
        BotCommand("unlink", "Unlink your account"),
        BotCommand("cancel", "Cancel current action"),
    ]
    try:
        await app.bot.set_my_commands(commands)
    except Exception:  # noqa: BLE001 - non-fatal (network/Telegram hiccup)
        logger.warning("Failed to register command menu: %r",
                       "set_my_commands failed")


# --------------------------------------------------------------- bot build
def build_application() -> Application:
    import os

    from cpd.config import (
        TELEGRAM_API_BASE_URL,
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
        CallbackQueryHandler(_on_start_option, pattern=r"^start\|"),
        CallbackQueryHandler(_on_menu, pattern=r"^menu\|"),
    ]

    reg_course_handlers = [
        CallbackQueryHandler(_on_reg_course, pattern=r"^reg\|"),
        CallbackQueryHandler(_on_start_option, pattern=r"^start\|"),
        CommandHandler("cancel", cmd_cancel),
    ]
    reg_identity_handlers = [
        MessageHandler(filters.TEXT & ~filters.COMMAND, _on_reg_identity),
        CommandHandler("cancel", cmd_cancel),
    ]
    reg_text_handlers = [
        MessageHandler(filters.TEXT & ~filters.COMMAND, _on_reg_license),
        CommandHandler("cancel", cmd_cancel),
    ]
    reg_name_handlers = [
        MessageHandler(filters.TEXT & ~filters.COMMAND, _on_reg_name),
        CommandHandler("cancel", cmd_cancel),
    ]
    reg_phone_handlers = [
        MessageHandler(filters.TEXT & ~filters.COMMAND, _on_reg_phone),
        CommandHandler("cancel", cmd_cancel),
    ]
    reg_location_handlers = [
        MessageHandler(filters.TEXT & ~filters.COMMAND, _on_reg_location),
        CommandHandler("cancel", cmd_cancel),
    ]
    reg_payment_handlers = [
        CallbackQueryHandler(_on_pay_check, pattern=r"^pay\|check"),
        CallbackQueryHandler(_on_pay_cancel, pattern=r"^pay\|cancel"),
        CommandHandler("cancel", cmd_cancel),
    ]

    conversation = ConversationHandler(
        entry_points=[
            CommandHandler("start", cmd_start),
            CommandHandler("view", cmd_view),
        ],
        states={
            START_OPTIONS: shared_handlers,
            NAME: shared_handlers,
            MENU: shared_handlers,
            REG_IDENTITY: reg_identity_handlers,
            REG_COURSE: reg_course_handlers,
            REG_LICENSE: reg_text_handlers,
            REG_NAME: reg_name_handlers,
            REG_PHONE: reg_phone_handlers,
            REG_LOCATION: reg_location_handlers,
            REG_PAYMENT: reg_payment_handlers,
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
        ],
    )

    builder = Application.builder().token(TELEGRAM_BOT_TOKEN)
    if TELEGRAM_API_BASE_URL:
        builder = builder.base_url(TELEGRAM_API_BASE_URL)
    builder.post_init(_register_commands)
    application = (
        builder
        .connect_timeout(CONNECT_TIMEOUT)
        .read_timeout(READ_TIMEOUT)
        .write_timeout(READ_TIMEOUT)
        .pool_timeout(READ_TIMEOUT)
        .build()
    )
    application.add_handler(conversation)
    application.add_handler(CommandHandler("myid", cmd_myid))
    application.add_handler(CommandHandler("unlink", cmd_unlink))
    application.add_handler(CommandHandler("admin_list", cmd_admin_list))
    application.add_handler(CommandHandler("admin_link", cmd_admin_link))
    application.add_handler(CommandHandler("admin_unlink", cmd_admin_unlink))
    application.add_handler(CommandHandler("admin_view", cmd_admin_view))
    application.add_handler(CommandHandler("admin_group", cmd_admin_group))
    application.add_handler(CommandHandler("admin_group_clear", cmd_admin_group_clear))
    application.add_handler(CommandHandler("admin_setup", cmd_admin_setup))
    application.add_handler(CommandHandler("admin_regs", cmd_admin_regs))
    application.add_handler(CommandHandler("admin_confirm", cmd_admin_confirm))
    application.add_handler(CommandHandler("admin", cmd_admin))
    application.add_handler(CommandHandler("admin_groups", cmd_admin_groups))
    application.add_handler(CommandHandler("admin_group_rename", cmd_admin_group_rename))
    application.add_handler(CommandHandler("admin_reg_del", cmd_admin_reg_del))
    application.add_handler(CommandHandler("admin_reg_clear", cmd_admin_reg_clear))
    application.add_handler(CommandHandler("admin_kick", cmd_admin_kick))
    application.add_error_handler(_error_handler)

    # Automatic Bakong payment confirmation: poll every 20s and finalise any
    # registration whose KHQR payment has landed.
    from cpd.payments import payment_enabled
    if payment_enabled() and application.job_queue is not None:
        application.job_queue.run_repeating(_payment_poll_job, interval=20,
                                            first=20, name="cpd_payment_poll")

    # Automatic Bakong token renewal: check shortly after startup and again on
    # the configured cadence (default every 24 days). Renews whenever the token
    # is missing or expires within BAKONG_TOKEN_RENEW_DAYS.
    from cpd.config import BAKONG_EMAIL, BAKONG_TOKEN_RENEW_DAYS
    if BAKONG_EMAIL and application.job_queue is not None:
        application.job_queue.run_repeating(
            _bakong_token_renew_job,
            interval=BAKONG_TOKEN_RENEW_DAYS * 86400,
            first=30,
        )
    return application


async def _bakong_token_renew_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Background job: renew the Bakong token when it is due."""
    import asyncio

    from cpd.bakong_token import renew_if_due

    renewed, message = await asyncio.to_thread(renew_if_due)
    if renewed:
        logger.info("Bakong token renewed automatically: %s", message)
        # With a live token now available, start the payment poll job if it
        # was not running yet.
        from cpd.payments import payment_enabled
        if payment_enabled() and context.job_queue is not None:
            jobs = [j for j in context.job_queue.jobs()
                    if j.name == "cpd_payment_poll"]
            if not jobs:
                context.job_queue.run_repeating(_payment_poll_job, interval=20,
                                                first=20, name="cpd_payment_poll")
    else:
        logger.info("Bakong token check: %s", message)


async def _payment_poll_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Background job: finalise registrations whose payment is confirmed."""
    from cpd.payments import poll_ready_payments
    for pending in poll_ready_payments():
        try:
            await _finalize_paid_registration(context, pending)
        except Exception:  # noqa: BLE001 - never crash the job
            logger.warning("Failed to finalise payment for chat %s",
                           pending.chat_id, exc_info=True)


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