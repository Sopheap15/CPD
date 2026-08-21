"""Course registration conversation handler, including the ABA payment step."""

from __future__ import annotations

import asyncio
import logging
import os
import traceback
import uuid
from pathlib import Path
from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from cpd.constants import (
    REG_COURSE,
    REG_IDENTITY,
    REG_LICENSE,
    REG_LOCATION,
    REG_NAME,
    REG_PAYMENT,
    REG_PHONE,
    REG_RECEIPT,
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
    generate_payment_ref,
    has_duplicate,
    registration_by_name,
)
from cpd.services.storage import get_linked_name, link_account


def _course_buttons(courses) -> InlineKeyboardMarkup:
    """Inline buttons for every open course."""
    rows = [
        [InlineKeyboardButton(
            f"{idx}. {c.title} — {c.date}" if c.date else f"{idx}. {c.title}",
            callback_data=f"reg|{c.course_id}",
        )]
        for idx, c in enumerate(courses, start=1)
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
    blocks = []
    for idx, c in enumerate(open_courses(data), start=1):
        block = f"<b>{idx}.</b> <b>{escape(c.title)}</b>"
        same_day = bool(c.end) and c.end[:10] == c.date[:10]
        if c.date and c.end and not same_day:
            # Multi-day course: show start and end separately.
            block += f"\n  🗓️ ចាប់ផ្តើម (Start): {escape(c.date)}"
            block += f"\n  🏁 បញ្ចប់ (End): {escape(c.end)}"
        elif c.date:
            block += f"\n  🗓️ កាលបរិច្ឆេទ (Date): {escape(c.date[:10] if same_day else c.date)}"
            if same_day:
                start_t = c.date[11:]
                end_t = c.end[11:]
                if start_t or end_t:
                    times = " - ".join(t for t in (start_t, end_t) if t)
                    block += f"\n  ⏰ ម៉ោង (Time): {escape(times)}"
        if c.cpd_points:
            block += f"\n  ⭐ ពិន្ទុ CPD (CPD Points): {escape(c.cpd_points)}"
        if c.fee:
            fee = f"{c.fee:.2f}".rstrip("0").rstrip(".")
            block += f"\n  💵 ថ្លៃ (Fee): ${fee}"
        blocks.append(block)
    text = "<b>📚 សូមជ្រើសរើសវគ្គបណ្តុះបណ្តាល (Choose a course):</b>\n\n"
    text += "\n\n".join(blocks)
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
        # No fee configured -> register immediately without payment.
        return await complete_registration(update, context, participant)

    # No longer appending a 'Pending payment' row.
    # The registration will only be recorded once the payment is verified.
    amount = f"{pending.amount:.2f}"
    pay_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ " + t("pay_check_button"), callback_data="pay|check")],
        [InlineKeyboardButton(t("pay_cancel_button"), callback_data="pay|cancel")],
    ])
    caption = fmt("pay_intro", course=escape(course.title),
                  amount=amount, currency="USD")
    try:
        with open("aba.png", "rb") as fh:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=fh,
                caption=caption,
                parse_mode="HTML",
                reply_markup=pay_kb,
            )
    except Exception as e:
        logging.getLogger(__name__).error(f"send_photo failed: {e}", exc_info=True)
        await safe_reply_html(update, caption, reply_markup=pay_kb)
    return REG_PAYMENT


async def on_pay_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Callback 'pay|check': ask the user to upload their ABA receipt for verification."""
    from cpd.services.payments import get_pending, payment_expired, drop_payment

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

    await safe_reply_html(
        update,
        "📷 សូមបញ្ចូលវិកាយបត្ររបស់អ្នក។"
    )
    return REG_RECEIPT


async def on_receipt_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Handle the uploaded receipt photo and verify it with local OCR."""
    from cpd.services.payments import get_pending, drop_payment, payment_expired
    from cpd.services.receipt_scanner import verify_receipt

    logger = logging.getLogger(__name__)
    chat_id = update.effective_chat.id

    pending = get_pending(chat_id)
    if pending is None or payment_expired(chat_id):
        await safe_reply_html(update, t("pay_expired"))
        clear_registration_state(context)
        return START_OPTIONS

    # Get the photo file
    message = update.effective_message
    if message and message.photo:
        photo = message.photo[-1]
        file_id = photo.file_id
    elif message and message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
        file_id = message.document.file_id
    else:
        await safe_reply_html(
            update,
            "❌ សូមបញ្ចូលរូបភាពវិកាយបត្ររបស់អ្នក។"
        )
        return REG_RECEIPT

    await safe_reply_html(update, "🔍 កំពុងពិនិត្យវិកាយបត្ររបស់អ្នក...")

    # Never let the receipt step hang: catch any failure.
    # Retry the download a few times - the Cloudflare Worker route can
    # drop connections transiently (httpx.ConnectError).
    img_bytes: bytes | None = None
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            file = await context.bot.get_file(file_id)

            # Download via the bot's own HTTP client so it respects the
            # Cloudflare/proxy configuration set in TELEGRAM_API_BASE_URL.
            img_bytes = bytes(await file.download_as_bytearray())
            last_exc = None
            break
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "Receipt download attempt %d/3 failed for chat %s: %s",
                attempt + 1, chat_id, exc,
            )
            await asyncio.sleep(1.5 * (attempt + 1))

    if img_bytes is None:
        exc_str = str(last_exc) if last_exc else "unknown error"
        if not exc_str:
            exc_str = type(last_exc).__name__ if last_exc else "UnknownError"
        logger.error("Receipt download failed for chat %s: %s", chat_id, exc_str)
        await safe_reply_html(
            update,
            f"⚠️ មិនអាចអានវិកាយបត្របានទេ។\n\n<b>Technical Error:</b> <code>{exc_str}</code>\n\n"
            "សូមផ្ញើរូបភាពច្បាស់ដាងនេះ ឬទាកទងអ្នករៀបចំ។",
        )
        return REG_RECEIPT

    try:
        # Write bytes to a local temp file for OCR (avoids Windows file locking)
        tmp_dir = Path("data/tmp")
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = str(tmp_dir / f"{uuid.uuid4()}.jpg")
        try:
            Path(tmp_path).write_bytes(img_bytes)
            del img_bytes  # free memory before spawning OCR thread

            # Run OCR in a separate thread so it doesn't block the async event loop
            loop = asyncio.get_running_loop()
            ok, reason, ref = await loop.run_in_executor(
                None, verify_receipt, tmp_path, pending.amount
            )
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    except Exception as exc:
        logger.error("Receipt download/OCR failed for chat %s: %s", chat_id, exc)
        exc_str = str(exc)
        if not exc_str:
            exc_str = type(exc).__name__
        await safe_reply_html(
            update,
            f"⚠️ មិនអាចអានវិកាយបត្របានទេ។\n\n<b>Technical Error:</b> <code>{exc_str}</code>\n\n"
            "សូមផ្ញើរូបភាពច្បាស់ដាងនេះ ឬទាកទងអ្នករៀបចំ។",
        )
        return REG_RECEIPT

    if ok:
        await finalize_paid_registration(context, pending, verified=True, ref=ref)
        clear_registration_state(context)
        return START_OPTIONS
    else:
        logger.warning("Receipt verification failed for chat %s: %s", chat_id, reason)
        cancel_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(t("pay_cancel_button"), callback_data="pay|cancel")],
        ])
        
        # Determine if we should ask for a clearer photo
        suffix = "\n\n📷 សូមផ្ញើរូបភាពវិកាយបត្រច្បាស់ជាងនេះ ឬចុចលុបចោល។"
        if "ធ្លាប់ត្រូវបានប្រើរួចហើយ" in reason:
            suffix = ""
            
        await safe_reply_html(
            update,
            f"{reason}{suffix}",
            reply_markup=cancel_kb,
        )
        return REG_RECEIPT


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
    try:
        await query.edit_message_text(t("cancel"), parse_mode="HTML")
    except BadRequest:
        await query.edit_message_caption(caption=t("cancel"), parse_mode="HTML")
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
        "payment_ref": generate_payment_ref(),
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
              date=now_str())
    await safe_reply_html(update, msg)

    await offer_group_join(context, chat_id, course)

    clear_registration_state(context)
    await send_start_message(context, chat_id)
    return START_OPTIONS


async def finalize_paid_registration(context: ContextTypes.DEFAULT_TYPE,
                                     pending, verified: bool = True,
                                     ref: str | None = None) -> None:
    """Complete a registration after payment confirmation.

    ``verified=True`` means OCR confirmed the receipt. ``verified=False`` means
    the receipt could not be auto-verified — registration is saved as Unverified.
    ``ref`` is the receipt reference extracted by OCR; recording it prevents
    the same receipt from being used again (anti-replay).
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

    # Payment is verified; record the registration permanently.
    append_registration({
        "telegram_id": pending.telegram_id,
        "name": participant.name,
        "participant_id": participant.participant_id,
        "phone": participant.phone,
        "location": participant.department,
        "course_id": course.course_id,
        "course_title": course.title,
        "course_date": course.date,
        "cpd_points": course.cpd_points,
        "fee": course.fee,
        "currency": "USD",
        "bill_number": pending.bill_number,
        "payment_ref": ref or generate_payment_ref(),
        "status": "Paid" if verified else "Unverified",
    })
    drop_payment(chat_id)

    if participant.name and get_linked_name(pending.telegram_id) is None:
        link_account(pending.telegram_id, participant.name)

    try:
        payment_line = fmt(
            "payment_line_ok" if verified else "payment_line_pending",
            amount=amount, currency="USD")
        await context.bot.send_message(
            chat_id,
            fmt("reg_confirm_paid",
                course=escape(course.title),
                name=escape(participant.name or ""),
                license=escape(participant.participant_id or "-"),
                phone=escape(participant.phone or "-"),
                location=escape(participant.department or "-"),
                date=now_str(),
                payment_line=payment_line),
            parse_mode="HTML",
        )
    except Exception:  # noqa: BLE001 - Telegram hiccup; non-fatal
        pass

    await offer_group_join(context, chat_id, course)
    await send_start_message(context, chat_id)
