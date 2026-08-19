"""Course registration conversation, including the Bakong payment step."""

from __future__ import annotations

from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from cpd.config import BAKONG_CURRENCY
from cpd.constants import (
    REG_COURSE,
    REG_IDENTITY,
    REG_LICENSE,
    REG_LOCATION,
    REG_NAME,
    REG_PAYMENT,
    REG_PHONE,
    START_OPTIONS,
)
from cpd.handlers.common import (
    _cpd,
    _is_admin,
    clear_registration_state,
    escape,
    now_str,
    safe_reply_html,
    send_start_message,
)
from cpd.handlers.groups import offer_group_join
from cpd.i18n import fmt, t
from cpd.services.registrations import (
    append_registration,
    has_duplicate,
    mark_paid,
    registration_by_name,
)
from cpd.services.storage import get_linked_name, link_account


def _course_buttons(courses) -> InlineKeyboardMarkup:
    """Inline buttons for every open course."""
    rows = [
        [InlineKeyboardButton(
            f"{c.title} — {c.date}" if c.date else c.title,
            callback_data=f"reg|{c.course_id}",
        )]
        for c in courses
    ]
    rows.append([InlineKeyboardButton("⬅️ ត្រឡប់ក្រោយ (Back)",
                                      callback_data="start|back")])
    return InlineKeyboardMarkup(rows)


def open_courses(data) -> list:
    return [
        c for c in data.courses
        if c.status.strip().lower() not in ("done", "completed", "ចប់")
    ]


def _course_list_text(data) -> str:
    """The 'Choose a course' listing with date, points and fee."""
    text = "<b>📚 សូមជ្រើសរើសវគ្គបណ្តុះបណ្តាល (Choose a course):</b>\n\n"
    for c in open_courses(data):
        text += f"• <b>{escape(c.title)}</b>\n"
        if c.date:
            text += f"  🗓️ កាលបរិច្ឆេទ (Date): {escape(c.date)}\n"
        if c.cpd_points:
            text += f"  ⭐ ពិន្ទុ CPD (CPD Points): {escape(c.cpd_points)}\n"
        if c.fee:
            fee = f"{c.fee:.2f}".rstrip("0").rstrip(".")
            text += f"  💵 ថ្លៃ (Fee): ${fee}\n"
    text += "\n\n" + t("further_info")
    return text


async def resolve_known_participant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Return a participant this user is already known as, or None.

    Checks (in order): Telegram-linked account, then any previous in-bot
    registration. This lets returning users skip all questions.
    """
    from cpd.services.search import exact_participant

    data = _cpd(context)
    linked_name = get_linked_name(update.effective_user.id)
    if linked_name:
        participant = exact_participant(data.participants, linked_name) or \
            next((p for p in data.participants if p.name == linked_name), None)
        if participant is not None and (participant.participant_id or participant.phone):
            return participant

    from cpd.services.data_loader import Participant
    prior = _latest_registration_for_user(update.effective_user.id)
    if prior is not None:
        return Participant(
            participant_id=prior.get("participant_id", ""),
            name=prior.get("name", ""),
            phone=prior.get("phone", ""),
            department=prior.get("location", ""),
        )
    return None


def _latest_registration_for_user(telegram_id: int) -> dict | None:
    from cpd.services.registrations import load_registrations
    rows = [r for r in load_registrations()
            if str(r.get("telegram_id", "")).strip() == str(telegram_id).strip()
            and r.get("name")]
    if not rows:
        return None
    rows.sort(key=lambda r: r.get("registered_at", ""))
    return rows[-1]


async def show_registration_courses(update: Update,
                                    context: ContextTypes.DEFAULT_TYPE) -> str:
    """Show the course list (edits the current menu message)."""
    query = update.callback_query
    data = _cpd(context)
    courses = open_courses(data)
    if not courses:
        text = ("គ្មានវគ្គបណ្តុះបណ្តាលសម្រាប់ការចុះឈ្មោះទេនៅពេលនេះ។ "
                "(No courses available for registration at this time.)")
        await query.edit_message_text(text, parse_mode="HTML",
                                      reply_markup=InlineKeyboardMarkup([
                                          [InlineKeyboardButton(
                                              "⬅️ ត្រឡប់ក្រោយ (Back)",
                                              callback_data="start|back")]
                                      ]))
        return START_OPTIONS
    await query.edit_message_text(_course_list_text(data), parse_mode="HTML",
                                  disable_web_page_preview=True,
                                  reply_markup=_course_buttons(courses))
    return REG_COURSE


async def send_courses_as_message(update: Update,
                                  context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the course list as a fresh message (used after text identification)."""
    data = _cpd(context)
    await update.effective_message.reply_html(
        _course_list_text(data),
        disable_web_page_preview=True,
        reply_markup=_course_buttons(open_courses(data)),
    )


async def on_reg_identity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """User typed a license number or full name to identify themselves."""
    from cpd.services.data_loader import Participant
    from cpd.services.search import (
        exact_participant,
        find_best,
        find_participant_by_secret,
    )

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
        await send_courses_as_message(update, context)
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


async def on_reg_license(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    license_val = (update.effective_message.text or "").strip()
    if not license_val:
        await safe_reply_html(update, t("reg_ask_license"))
        return REG_LICENSE
    context.user_data["reg_license"] = license_val

    # If this license already exists in the records, reuse that person's
    # name/phone so they don't have to re-enter anything.
    from cpd.services.search import find_participant_by_secret
    data = _cpd(context)
    known = find_participant_by_secret(data.participants, license_val)
    if known is not None:
        context.user_data["reg_participant"] = known
        context.user_data["reg_name"] = known.name or ""
        context.user_data["reg_phone"] = known.phone or ""
        context.user_data["reg_location"] = known.department or ""
        await send_courses_as_message(update, context)
        return REG_COURSE

    # Name already given at the identity step -> skip straight to phone.
    if context.user_data.get("reg_name"):
        await safe_reply_html(update, t("reg_ask_phone"))
        return REG_PHONE
    await safe_reply_html(update, t("reg_ask_name"))
    return REG_NAME


async def on_reg_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    name = (update.effective_message.text or "").strip()
    if not name:
        await safe_reply_html(update, t("reg_ask_name"))
        return REG_NAME
    context.user_data["reg_name"] = name
    await safe_reply_html(update, t("reg_ask_phone"))
    return REG_PHONE


async def on_reg_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    phone = (update.effective_message.text or "").strip()
    if not phone:
        await safe_reply_html(update, t("reg_ask_phone"))
        return REG_PHONE
    context.user_data["reg_phone"] = phone
    await safe_reply_html(update, t("reg_ask_location"))
    return REG_LOCATION


async def on_reg_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    location = (update.effective_message.text or "").strip()
    if not location:
        await safe_reply_html(update, t("reg_ask_location"))
        return REG_LOCATION
    context.user_data["reg_location"] = location

    from cpd.services.data_loader import Participant
    participant = Participant(
        participant_id=context.user_data.get("reg_license", ""),
        name=context.user_data.get("reg_name", ""),
        phone=context.user_data.get("reg_phone", ""),
        department=location,
    )
    context.user_data["reg_participant"] = participant
    await send_courses_as_message(update, context)
    return REG_COURSE


async def on_reg_course(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
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
    if has_duplicate(update.effective_user.id, course.course_id):
        await safe_reply_html(update, t("reg_already"))
        await offer_group_join(context, update.effective_chat.id, course)
        clear_registration_state(context)
        await send_start_message(context, update.effective_chat.id)
        return START_OPTIONS

    return await start_payment(update, context, course, participant)


async def start_payment(update: Update, context: ContextTypes.DEFAULT_TYPE,
                        course, participant) -> str:
    """Create the KHQR for the course fee and show it to the participant.

    Returns ``REG_PAYMENT`` so the bot waits for the payment callback, or
    registers the participant directly when no payment is required / not
    configured.
    """
    from cpd.services.payments import create_payment

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
        return await complete_registration(update, context, participant)

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


async def on_pay_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Callback 'pay|check': confirm payment and finish registration."""
    from cpd.services.payments import (
        check_payment,
        drop_payment,
        get_pending,
        payment_expired,
    )

    query = update.callback_query
    if query is None:
        return REG_PAYMENT
    await query.answer()
    chat_id = update.effective_chat.id

    pending = get_pending(chat_id)
    if pending is None:
        await safe_reply_html(update, t("pay_expired"))
        clear_registration_state(context)
        return START_OPTIONS
    if payment_expired(chat_id):
        drop_payment(chat_id)
        await safe_reply_html(update, t("pay_expired"))
        clear_registration_state(context)
        return START_OPTIONS

    # Without a Bakong token we can't poll the transaction, so a manual
    # "I have paid" is treated as confirmation (Unverified, admin confirms later).
    if check_payment(chat_id) or not pending.user_data.get("can_verify", True):
        await finalize_paid_registration(context, pending,
                                         verified=check_payment(chat_id))
        clear_registration_state(context)
        return START_OPTIONS
    await safe_reply_html(update, t("pay_unpaid"))
    return REG_PAYMENT


async def on_pay_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Callback 'pay|cancel': drop the pending payment and the registration."""
    from cpd.services.payments import drop_payment

    query = update.callback_query
    if query is None:
        return REG_PAYMENT
    await query.answer()
    chat_id = update.effective_chat.id
    drop_payment(chat_id)
    clear_registration_state(context)
    await query.edit_message_text(t("cancel"), parse_mode="HTML")
    await send_start_message(context, chat_id)
    return START_OPTIONS


async def complete_registration(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                participant) -> str:
    """Save a free (non-payment) registration and confirm it."""
    course = context.user_data.get("reg_course")
    if course is None:
        await safe_reply_html(update, t("reg_pick_course"))
        return REG_COURSE
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

    if participant.name and get_linked_name(update.effective_user.id) is None:
        link_account(update.effective_user.id, participant.name)

    msg = fmt("reg_confirm_new" if participant.name else "reg_confirm_old",
              course=escape(course.title),
              name=escape(participant.name or ""),
              license=escape(participant.participant_id or "-"),
              phone=escape(participant.phone or "-"),
              location=escape(participant.department or "-"),
              telegram_id=update.effective_user.id,
              date=now_str())
    await safe_reply_html(update, msg)

    await offer_group_join(context, chat_id, course)

    clear_registration_state(context)
    await send_start_message(context, chat_id)
    return START_OPTIONS


async def finalize_paid_registration(context: ContextTypes.DEFAULT_TYPE,
                                     pending, verified: bool = True) -> None:
    """Complete a registration after payment confirmation.

    ``verified=True`` means Bakong confirmed the transaction (or auto-verification
    is configured). ``verified=False`` is a manual "I have paid" tap when the
    developer token is still missing — the registration is saved as Unverified.
    """
    from cpd.services.data_loader import Course, Participant
    from cpd.services.payments import drop_payment

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
                date=now_str(),
                payment_line=payment_line),
            parse_mode="HTML",
        )
    except Exception:  # noqa: BLE001 - Telegram hiccup; non-fatal
        pass

    await offer_group_join(context, chat_id, course)
    await send_start_message(context, chat_id)
