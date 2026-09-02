"""Certificate pickup: record who collected a trainee's certificate(s).

A trainee may collect their own certificate(s) or send someone else to do
it. The flow first asks who is collecting (the owner or someone else), then
asks for the trainee's name, and only when the collector is a different
person also asks for that person's name. Finally the user selects which
completed course certificate is being collected. The pickup is saved to the
same CSV file that already holds the pharmacist's name
(in_bot_registrations.csv), including the course so it's clear which
certificate was picked up.
"""

from __future__ import annotations

from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from cpd.constants import (
    PICKUP_COURSE,
    PICKUP_NAME,
    PICKUP_PICKER,
    PICKUP_WHO,
    START_OPTIONS,
)
from cpd.config import ADMIN_IDS
from cpd.handlers.common import _cpd, _start_keyboard, now_str, safe_reply_html
from cpd.i18n import fmt, t
from cpd.services.data_loader import Participant
from cpd.services.registrations import (
    append_pickup,
    load_registrations,
)
from cpd.services.search import (
    exact_participant,
    find_participant_by_secret,
    normalize_name,
)


def _pickup_who_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🙋 " + t("pickup_self"), callback_data="pickup|self")],
        [InlineKeyboardButton("🤝 " + t("pickup_other"), callback_data="pickup|other")],
        [InlineKeyboardButton("❌ " + t("cancel"), callback_data="pickup|cancel")],
    ])


def done_courses(data) -> list:
    """Courses whose status marks them as finished (certificate available)."""
    return [
        c for c in data.courses
        if c.status.strip().lower() in ("done", "completed", "ចប់")
    ]


def _resolve_pickup_participant(data, query: str):
    """Strictly resolve a trainee for pickup.

    The person must genuinely exist in the system (master participant list,
    trainings, or certificates). A name that matches nobody is rejected so the
    user cannot record a pickup against a phantom person. The user may also
    type a license number / phone as an alternative search.
    """

    by_secret = find_participant_by_secret(data.participants, query)
    if by_secret is not None:
        return by_secret

    by_name = exact_participant(data.participants, query)
    if by_name is not None:
        return by_name

    norm_query = normalize_name(query)
    for t_rec in data.trainings:
        if normalize_name(t_rec.participant_name) == norm_query:
            return Participant(participant_id=t_rec.participant_id, name=query)
    for c_rec in data.certificates:
        if normalize_name(c_rec.participant_name) == norm_query or \
                normalize_name(c_rec.khmer_name) == norm_query:
            return Participant(
                participant_id=c_rec.participant_id,
                name=c_rec.participant_name or query,
                khmer_name=c_rec.khmer_name,
            )
    return None


def picked_up_course_ids(name: str) -> set[str]:
    """Course ids already collected for this trainee from pickup rows."""

    key = (name or "").strip().lower()
    ids: set[str] = set()
    for r in load_registrations():
        if (r.get("status") or "").strip() != "Picked up":
            continue
        if (r.get("name") or "").strip().lower() != key:
            continue
        cid = (r.get("course_id") or "").strip()
        if cid:
            ids.add(cid)
    return ids


def learned_course_ids(data, name: str) -> set[str]:
    """Course ids the trainee registered for / actually attended.

    Sources:
      * in-bot registrations (course_id recorded per name), and
      * trainings/certificates whose title or date matches a known course.
    A course that nobody attended is not offered for pickup.
    """

    key = (name or "").strip().lower()
    ids: set[str] = set()

    for r in load_registrations():
        if (r.get("name") or "").strip().lower() != key:
            continue
        cid = (r.get("course_id") or "").strip()
        if cid:
            ids.add(cid)

    courses = list(data.courses)
    for t in data.trainings:
        if normalize_name(t.participant_name) != key:
            continue
        for c in courses:
            if c.course_id in ids:
                continue
            c_title = normalize_name(c.title or "")
            t_title = normalize_name(t.title or "")
            c_date = normalize_name(c.date or "")
            t_date = normalize_name(t.date or "")
            if c_title and (c_title in t_title or t_title in c_title):
                ids.add(c.course_id)
            elif c_date and (c_date in t_date or t_date in c_date):
                ids.add(c.course_id)

    for cert in data.certificates:
        if normalize_name(cert.participant_name) != key and \
                normalize_name(cert.khmer_name or "") != key:
            continue
        for c in courses:
            if c.course_id in ids:
                continue
            c_date = normalize_name(c.date or "")
            t_date = normalize_name(cert.training_title or "")
            if c_date and (c_date in t_date or t_date in c_date):
                ids.add(c.course_id)

    return ids


def available_courses(data, name: str) -> list:
    """Done + certificate-ready courses the trainee attended, not yet picked up."""
    picked = picked_up_course_ids(name)
    learned = learned_course_ids(data, name)
    return [
        c for c in done_courses(data)
        if c.certificate_ready
        and c.course_id in learned and c.course_id not in picked
    ]


def not_ready_courses(data, name: str) -> list:
    """Done courses the trainee attended whose certificate is not yet ready."""
    picked = picked_up_course_ids(name)
    learned = learned_course_ids(data, name)
    return [
        c for c in done_courses(data)
        if not c.certificate_ready
        and c.course_id in learned and c.course_id not in picked
    ]


def _course_buttons(courses, selected: list[str]) -> InlineKeyboardMarkup:
    rows = []
    for c in courses:
        mark = "✅ " if c.course_id in selected else ""
        rows.append([InlineKeyboardButton(
            f"{mark}{c.title} — {c.date}" if c.date else f"{mark}{c.title}",
            callback_data=f"pickup|course|{c.course_id}",
        )])
    rows.append([InlineKeyboardButton(
        "✅ " + t("pickup_confirm"), callback_data="pickup|confirm")])
    rows.append([InlineKeyboardButton("⬅️ " + t("cancel"),
                                      callback_data="pickup|cancel")])
    return InlineKeyboardMarkup(rows)


async def start_pickup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Entry point for the certificate pickup flow (button 3)."""
    query = update.callback_query
    if query is not None:
        await query.answer()
        await query.edit_message_text(t("pickup_who"), parse_mode="HTML",
                                      reply_markup=_pickup_who_keyboard())
    else:
        await safe_reply_html(update, t("pickup_who"),
                              reply_markup=_pickup_who_keyboard())
    context.user_data.pop("pickup_name", None)
    context.user_data.pop("pickup_is_other", None)
    context.user_data.pop("pickup_selected", None)
    return PICKUP_WHO


async def on_pickup_who(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    query = update.callback_query
    if query is None:
        return PICKUP_WHO
    await query.answer()
    action = query.data.split("|", 1)[1]

    if action == "cancel":
        _clear(context)
        await query.edit_message_text(t("pickup_cancel"), parse_mode="HTML")
        return START_OPTIONS

    if action in ("self", "other"):
        context.user_data["pickup_is_other"] = (action == "other")
        await query.edit_message_text(t("pickup_ask_name"), parse_mode="HTML")
        return PICKUP_NAME

    return PICKUP_WHO


async def on_pickup_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Resolve the entered trainee name, then ask who is collecting."""
    name = (update.effective_message.text or "").strip()
    if not name:
        await safe_reply_html(update, t("pickup_ask_name"))
        return PICKUP_NAME

    data = _cpd(context)
    participant = _resolve_pickup_participant(data, name)
    if participant is None:
        await safe_reply_html(update, fmt("pickup_name_not_found", name=escape(name)))
        return PICKUP_NAME

    context.user_data["pickup_name"] = participant.name or name

    # Only ask who is collecting after confirming there is a certificate to
    # collect. Without this check the user would enter the picker's name and
    # only then be told there is nothing to pick up.
    courses = available_courses(data, participant.name or name)
    if not courses:
        not_ready = not_ready_courses(data, participant.name or name)
        if not_ready:
            labels = "".join(
                f"• {escape(c.title)} — {escape(c.date)}\n"
                for c in not_ready
            )
            await safe_reply_html(
                update,
                fmt("pickup_not_ready",
                    name=escape(participant.name or name), courses=labels),
            )
        else:
            await safe_reply_html(update, t("pickup_no_courses"))
        _clear(context)
        return START_OPTIONS

    if context.user_data.get("pickup_is_other"):
        await safe_reply_html(update, t("pickup_ask_picker"))
        return PICKUP_PICKER

    return await _ask_course(update, context)


async def on_pickup_picker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Store the collector's name when it is someone other than the trainee."""
    picker = (update.effective_message.text or "").strip()
    if not picker:
        await safe_reply_html(update, t("pickup_ask_picker"))
        return PICKUP_PICKER
    context.user_data["pickup_picker"] = picker
    return await _ask_course(update, context)


async def _ask_course(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    data = _cpd(context)
    name = context.user_data.get("pickup_name", "")
    courses = available_courses(data, name)
    if not courses:
        not_ready = not_ready_courses(data, name)
        if not_ready:
            labels = "".join(
                f"• {escape(c.title)} — {escape(c.date)}\n"
                for c in not_ready
            )
            await safe_reply_html(
                update,
                fmt("pickup_not_ready", name=escape(name), courses=labels),
            )
        else:
            await safe_reply_html(update, t("pickup_no_courses"))
        return START_OPTIONS

    context.user_data["pickup_selected"] = []
    text = t("pickup_ask_course")
    await safe_reply_html(update, text, reply_markup=_course_buttons(courses, []))
    return PICKUP_COURSE


async def on_pickup_course(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    query = update.callback_query
    if query is None:
        return PICKUP_COURSE
    await query.answer()
    parts = query.data.split("|")
    if len(parts) < 2:
        return PICKUP_COURSE

    if parts[1] == "cancel":
        _clear(context)
        await query.edit_message_text(t("pickup_cancel"), parse_mode="HTML")
        return START_OPTIONS

    data = _cpd(context)
    name = context.user_data.get("pickup_name", "")
    courses = available_courses(data, name)
    selected = context.user_data.get("pickup_selected", [])

    if parts[1] == "confirm":
        if not selected:
            await safe_reply_html(update, t("pickup_confirm_none"))
            return PICKUP_COURSE
        return await _save_pickup(update, context, courses, selected)

    course_id = parts[2] if len(parts) > 2 else ""
    if course_id in selected:
        selected.remove(course_id)
    else:
        selected.append(course_id)
    context.user_data["pickup_selected"] = selected

    text = t("pickup_ask_course") + "\n\n" + "".join(
        f"• {'✅' if c.course_id in selected else '⬜️'} <b>{escape(c.title)}</b>"
        f"{' — ' + escape(c.date) if c.date else ''}\n"
        for c in courses
    )
    await query.edit_message_text(
        text, parse_mode="HTML", reply_markup=_course_buttons(courses, selected))
    return PICKUP_COURSE


async def _save_pickup(
    update: Update, context: ContextTypes.DEFAULT_TYPE,
    courses, selected: list[str],
) -> str:
    """Write one pickup row per selected course using the shared info."""
    query = update.callback_query
    name = context.user_data.get("pickup_name", "")
    picker = context.user_data.get("pickup_picker", "") or name

    for course in courses:
        if course.course_id in selected:
            append_pickup(name, picker, course_id=course.course_id,
                          course_title=course.title, course_date=course.date)

    picked = [c for c in courses if c.course_id in selected]
    labels = ", ".join(f"<b>{escape(c.title)}</b>" for c in picked)


    time_str = now_str("%Y-%m-%d %H:%M")
    if picker:
        text = fmt("pickup_saved_by", name=name, courses=labels,
                   time=time_str, by=picker)
    else:
        text = fmt("pickup_saved", name=name, courses=labels, time=time_str)

    try:
        await query.edit_message_text(
            text, parse_mode="HTML", reply_markup=_start_keyboard())
    except Exception:  # noqa: BLE001
        await safe_reply_html(update, text, reply_markup=_start_keyboard())

    await _notify_admins(update, context, name, picked, picker, time_str)

    # Remember who was just recorded so the next "View History" click shows
    # this trainee's report instead of asking for verification again.
    context.user_data["last_view_name"] = name

    _clear(context)
    return START_OPTIONS


async def _notify_admins(update: Update, context: ContextTypes.DEFAULT_TYPE,
                         name: str, picked, picker: str, time_str: str) -> None:
    """Alert admins so they can find and prepare the certificate(s)."""
    if not ADMIN_IDS:
        return

    sender = update.effective_user
    by = escape(picker) if picker else "🙋 " + t("pickup_self")
    lines = "".join(
        f"• {escape(c.title)} ({escape(c.date) if c.date else '-'})\n"
        for c in picked
    )
    text = fmt("pickup_admin_alert", name=escape(name), courses=lines,
               time=time_str, by=by, sender=sender.full_name if sender else "-")
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "📊 " + t("view_history"),
            callback_data=f"alert|view|{name}",
        ),
    ]])
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                admin_id, text, parse_mode="HTML", reply_markup=keyboard)
        except Exception:  # noqa: BLE001 - admin may not have started the bot
            pass


def _clear(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in ("pickup_name", "pickup_is_other", "pickup_picker",
                "pickup_selected"):
        context.user_data.pop(key, None)