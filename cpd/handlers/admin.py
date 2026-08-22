"""Admin-only commands: account linking, course groups and registrations."""

from __future__ import annotations

from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from cpd.handlers.common import _cpd, _is_admin, safe_reply_html
from cpd.handlers.history import show_summary
from cpd.handlers.registration import open_courses
from cpd.i18n import fmt, t
from cpd.services.course_groups import (
    all_group_mappings,
    clear_group_chat_id,
    get_group_chat_id,
    set_group_chat_id,
)
from cpd.services.registrations import (
    clear_registrations,
    delete_registration,
    load_registrations,
    mark_paid,
)
from cpd.services.storage import (
    admin_unlink_by_name,
    link_account,
    list_all_links,
    unlink_account,
)


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: /admin — show the admin command menu."""
    if not _is_admin(update):
        await safe_reply_html(update, t("admin_only"))
        return
    await safe_reply_html(update, t("admin_help"))


async def cmd_admin_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: list all linked accounts."""
    if not _is_admin(update):
        await safe_reply_html(update, t("admin_only"))
        return
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
    return await show_summary(update, context, " ".join(args))


async def auto_link_group(update: Update, context: ContextTypes.DEFAULT_TYPE,
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
    courses = open_courses(data)
    if not courses:
        await safe_reply_html(update, "No open courses to set up.")
        return
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
    clear_group_chat_id(course_id)
    await safe_reply_html(update, f"✅ Unlinked group for course <b>{escape(course_id)}</b>")


async def cmd_admin_regs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: /admin_regs — list all in-bot registrations (incl. pending fees)."""
    if not _is_admin(update):
        await safe_reply_html(update, t("admin_only"))
        return
    rows = load_registrations()
    if not rows:
        await safe_reply_html(update, "No registrations yet.")
        return
    lines = [f"<b>📝 Registrations ({len(rows)}):</b>"]
    for r in reversed(rows):
        name = escape(r.get("name", "") or "-")
        course = escape(r.get("course_title", "") or r.get("course_id", "") or "-")
        pay = escape(r.get("status", "") or "-")
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
    if mark_paid(bill, status="Paid"):
        await safe_reply_html(update,
            f"✅ Payment <code>{escape(bill)}</code> marked as <b>Paid</b>.")
    else:
        await safe_reply_html(update,
            f"❌ No registration found with bill number <code>{escape(bill)}</code>.")


async def cmd_admin_groups(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: /admin_groups — list course ↔ group chat IDs."""
    if not _is_admin(update):
        await safe_reply_html(update, t("admin_only"))
        return
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


def _bot_trainings_for_course(data, course) -> list:
    """Bot-registered participants (merged trainings) of one course."""
    title = (course.title or "").strip().lower()
    if not title:
        return []
    return [
        tr for tr in data.trainings
        if tr.source == "bot" and (tr.title or "").strip().lower() == title
    ]


async def _courses_overview(update: Update,
                            context: ContextTypes.DEFAULT_TYPE) -> None:
    """One summary line per course: registrations & pickups."""
    data = _cpd(context)
    lines = [t("admin_courses_title")]
    for c in data.courses:
        trs = _bot_trainings_for_course(data, c)
        total = len(trs)
        picked = sum(1 for tr in trs if tr.picked_up)
        icon = "✅" if total and picked == total else ("🎓" if picked else "📚")
        lines.append(fmt("admin_courses_line", icon=icon,
                         course=escape(c.course_id), total=total,
                         picked=picked))
    await safe_reply_html(update, "\n".join(lines))


async def cmd_admin_courses(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: /admin_courses [Course ID] — all courses, or one course's detail."""
    if not _is_admin(update):
        await safe_reply_html(update, t("admin_only"))
        return
    if context.args:
        # Same command accepts an ID so autocomplete mix-ups still work.
        await cmd_admin_course(update, context)
        return
    await _courses_overview(update, context)


async def cmd_admin_course(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: /admin_course [Course ID] — detail per course; without an ID
    it falls back to the overview so both spellings always answer."""
    if not _is_admin(update):
        await safe_reply_html(update, t("admin_only"))
        return
    args = context.args or []
    if not args:
        await _courses_overview(update, context)
        return
    course_id = args[0].strip().rstrip(".").upper()
    data = _cpd(context)
    course = next((c for c in data.courses
                   if c.course_id.strip().upper() == course_id.upper()), None)
    if course is None:
        ids = ", ".join(c.course_id for c in data.courses) or "—"
        await safe_reply_html(update, fmt("admin_course_notfound",
                                          course=escape(course_id),
                                          ids=escape(ids)))
        return

    trs = sorted(_bot_trainings_for_course(data, course),
                 key=lambda tr: (tr.participant_name or "").lower())
    total = len(trs)
    picked_n = sum(1 for tr in trs if tr.picked_up)
    pct = round(picked_n * 100 / total) if total else 0
    lines = [fmt("admin_course_title", course=escape(course.course_id),
                 title=escape(course.title), total=total, picked=picked_n,
                 pct=pct)]
    if not trs:
        lines.append(t("admin_course_empty"))
    for tr in trs:
        # Show the Khmer name next to the Latin one when we know it.
        khmer = ""
        for p in data.participants:
            if p.participant_id and p.participant_id == tr.participant_id \
                    and p.khmer_name:
                khmer = p.khmer_name
                break
        name = f"{khmer} / {tr.participant_name}" if khmer \
            else tr.participant_name
        when = (tr.pickup_date or "")[:16]
        if tr.picked_up:
            lines.append(fmt("admin_course_picked_line", name=escape(name),
                             date=escape(when)))
        else:
            lines.append(fmt("admin_course_pending_line", name=escape(name)))
    await safe_reply_html(update, "\n".join(lines))


async def cmd_admin_reg_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: /admin_reg_add <Course ID> <Full Name> — register someone who
    has no Telegram account (walk-in / cash payment) directly as Paid."""
    if not _is_admin(update):
        await safe_reply_html(update, t("admin_only"))
        return
    args = context.args or []
    if len(args) < 2:
        await safe_reply_html(update, t("admin_reg_add_usage"))
        return
    data = _cpd(context)
    course = None
    name_parts: list[str] = []
    # Accept the course ID as either the first or the last token.
    for idx in (0, len(args) - 1):
        cand = args[idx].strip().upper()
        course = next((c for c in data.courses
                       if c.course_id.strip().upper() == cand), None)
        if course is not None:
            name_parts = args[:idx] + args[idx + 1:]
            break
    if course is None:
        ids = ", ".join(c.course_id for c in data.courses) or "—"
        await safe_reply_html(update, fmt("admin_reg_add_notfound",
                                          course=escape(args[0]),
                                          ids=escape(ids)))
        return
    full_name = " ".join(name_parts).strip()
    if not full_name:
        await safe_reply_html(update, t("admin_reg_add_usage"))
        return

    from cpd.handlers.registration import _has_khmer
    from cpd.services.registrations import (
        append_registration,
        generate_payment_ref,
        load_registrations,
    )
    key = full_name.strip().lower()
    for r in load_registrations():
        if (r.get("course_id") or "").strip().upper() != course.course_id.upper():
            continue
        if (r.get("status") or "") not in ("Paid", "Registered", "Unverified"):
            continue
        names = {(r.get("name") or "").strip().lower(),
                 (r.get("khmer_name") or "").strip().lower()}
        if key in names:
            await safe_reply_html(update, fmt(
                "admin_reg_add_dup", name=escape(full_name),
                course=escape(course.course_id)))
            return

    record = {
        "name": "" if _has_khmer(full_name) else full_name,
        "khmer_name": full_name if _has_khmer(full_name) else "",
        "course_id": course.course_id,
        "course_title": course.title,
        "course_date": course.date,
        "cpd_points": course.cpd_points,
        "fee": course.fee,
        "currency": "USD",
        "payment_ref": generate_payment_ref(),
        "status": "Paid",
    }
    append_registration(record)
    await safe_reply_html(update, fmt(
        "admin_reg_add_ok", name=escape(full_name),
        course=escape(course.course_id), title=escape(course.title)))


async def cmd_admin_reg_move(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: /admin_reg_move <ID or Name> <From> <To> — move a registration.

    Keeps the payment record (bill, reference, status) and rewrites the
    course columns, so the participant appears under the new course without
    paying/registering again.
    """
    if not _is_admin(update):
        await safe_reply_html(update, t("admin_only"))
        return
    args = context.args or []
    if len(args) < 3:
        await safe_reply_html(update, t("admin_reg_move_usage"))
        return
    data = _cpd(context)

    def find_course(token: str):
        token = token.strip().upper()
        return next((c for c in data.courses
                     if c.course_id.strip().upper() == token), None)

    from_course = find_course(args[-2])
    to_course = find_course(args[-1])
    if from_course is None or to_course is None:
        ids = ", ".join(c.course_id for c in data.courses) or "—"
        bad = args[-2] if from_course is None else args[-1]
        await safe_reply_html(update, fmt("admin_reg_add_notfound",
                                          course=escape(bad), ids=escape(ids)))
        return
    if from_course.course_id == to_course.course_id:
        await safe_reply_html(update, t("admin_reg_move_same"))
        return

    who = " ".join(args[:-2]).strip()
    is_tid = who.lstrip("-").isdigit()

    from cpd.services.registrations import load_registrations, _write
    rows = load_registrations()
    target = None
    key = who.lower()
    for r in rows:
        if (r.get("course_id") or "").strip().upper() != from_course.course_id.upper():
            continue
        if is_tid:
            if str(r.get("telegram_id", "")).strip() == who:
                target = r
                break
        else:
            names = {(r.get("name") or "").strip().lower(),
                     (r.get("khmer_name") or "").strip().lower()}
            if key in names:
                target = r
                break
    if target is None:
        await safe_reply_html(update, fmt(
            "admin_reg_move_notfound", who=escape(who),
            course=escape(from_course.course_id)))
        return

    # Block the move when the person already sits in the destination course.
    names_t = {(target.get("name") or "").strip().lower(),
               (target.get("khmer_name") or "").strip().lower()}
    tid_t = str(target.get("telegram_id", "")).strip()
    for r in rows:
        if (r.get("course_id") or "").strip().upper() != to_course.course_id.upper():
            continue
        r_names = {(r.get("name") or "").strip().lower(),
                   (r.get("khmer_name") or "").strip().lower()}
        same_person = (
            (tid_t and str(r.get("telegram_id", "")).strip() == tid_t)
            or (key in r_names))
        if same_person and (r.get("status") or "") in ("Paid", "Registered",
                                                       "Unverified"):
            display = target.get("name") or target.get("khmer_name") or who
            await safe_reply_html(update, fmt(
                "admin_reg_move_dup", name=escape(display),
                course=escape(to_course.course_id)))
            return

    name = target.get("name") or target.get("khmer_name") or who
    target["course_id"] = to_course.course_id
    target["course_title"] = to_course.title
    target["course_date"] = to_course.date
    target["cpd_points"] = to_course.cpd_points
    target["fee"] = to_course.fee
    _write(rows)

    diff = round((to_course.fee or 0) - (from_course.fee or 0), 2)
    if diff > 0:
        fee_line = fmt("admin_reg_move_fee_up", amount=f"{diff:.2f}")
    elif diff < 0:
        fee_line = fmt("admin_reg_move_fee_down", amount=f"{abs(diff):.2f}")
    else:
        fee_line = ""
    await safe_reply_html(update, fmt(
        "admin_reg_move_ok", name=escape(name),
        from_course=escape(from_course.course_id),
        to_course=escape(to_course.course_id),
        title=escape(to_course.title), fee_line=fee_line))