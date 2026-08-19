"""CPD Track Telegram bot as a Cloudflare Python Worker (webhook mode).

This is a single-file, dependency-free port of the polling bot in ``cpd/``.
Cloudflare Python Workers run on Pyodide, so:

  * no pandas / openpyxl / python-telegram-bot (data arrives as JSON from KV)
  * no long-polling (Telegram calls our webhook URL)
  * no local filesystem (the telegram_id -> name links live in Cloudflare KV)

Data flow:

  1. ``scripts/export_data.py`` reads the Excel files locally and writes
     ``worker/data.json``.
  2. ``deploy.ps1`` (or the dashboard) uploads ``data.json`` to the KV
     namespace bound as ``CPD_KV`` and stores it under the key ``data``.
  3. ``links`` is a single KV key holding ``{telegram_id: participant_name}``.

The logic below mirrors the polling bot exactly (same messages, same fuzzy
search, same reports). The Worker entrypoint classes/imports are guarded so the
pure logic can be tested locally with a normal Python interpreter.
"""

from __future__ import annotations

import html
import json
import time
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

IS_WORKER = False
Response = None
fetch = None
console = None

try:  # only present inside the Cloudflare Workers Python runtime
    from workers import WorkerEntrypoint, Response  # type: ignore
    from js import fetch, console  # type: ignore

    IS_WORKER = True
except Exception:  # pragma: no cover - CPython fallback for local tests
    pass

NL = "\n"

# --------------------------------------------------------------------------- i18n
# key -> (english, khmer). The bot displays the Khmer string, mirroring cpd/i18n.py.
TRANSLATIONS: dict[str, tuple[str, str]] = {
    "welcome": (
        "Welcome! What can I help you with?",
        "សូមស្វាគមន៍! តើមានអ្វីដែលខ្ញុំអាចជួយអ្នកបានទេ?",
    ),
    "ask_name": (
        "Please enter your full name to view your CPD history (e.g. Sokha Chan).",
        "សូមបញ្ចូលឈ្មោះពេញរបស់អ្នកដើម្បីមើលប្រវត្តិ CPD (ឧទាហរណ៍៖ សុខា ចាន់ / Sokha Chan)។",
    ),
    "cancel": ("Search cancelled.", "បានលុបចោលការស្វែងរក។"),
    "ask_verification": (
        "Please enter your Name, Phone Number, or Participant ID to link your account and view your CPD history.",
        "សូមបញ្ចូល ឈ្មោះ, លេខទូរស័ព្ទ ឬ លេខសម្គាល់អ្នកចូលរួម របស់អ្នក ដើម្បីផ្ទៀងផ្ទាត់គណនី និងមើលប្រវត្តិ CPD របស់អ្នក។",
    ),
    "account_linked": (
        "Your account is linked successfully! Welcome {name}.",
        "គណនីរបស់អ្នកត្រូវបានភ្ជាប់ដោយជោគជ័យ! សូមស្វាគមន៍ {name}។",
    ),
    "not_found_verification": (
        "No participant found with that Phone Number or ID.\nPlease try again.",
        "រកមិនឃើញអ្នកចូលរួមដែលមានលេខទូរស័ព្ទ ឬ លេខសម្គាល់នោះទេ។\nសូមព្យាយាមម្ដងទៀត។",
    ),
    "not_found": (
        "No participant found with the name \"{name}\".\n"
        "Please check the spelling, or try your family name only (e.g. \"Chan\").",
        "រកមិនឃើញអ្នកចូលរួមដែលមានឈ្មោះ \"{name}\" ទេ។\n"
        "សូមពិនិត្យអក្ខរាវិរុទ្ធ ឬសាកល្បងតែគោត្តនាម (ឧ. \"ចាន់ / Chan\")។",
    ),
    "multiple_matches": (
        "I found {count} participants with a similar name. Please choose one:",
        "ខ្ញុំបានរកឃើញអ្នកចូលរួម {count} នាក់ដែលមានឈ្មោះប្រហាក់ប្រហែល។ សូមជ្រើសរើសមួយ៖",
    ),
    "section_training": ("Training History", "ប្រវត្តិបណ្ដុះបណ្ដាល"),
    "section_certificate": ("CPD Certificate Pickup", "ការទទួលវិញ្ញាបនបត្រ CPD"),
    "section_summary": ("Summary", "សង្ខេប"),
    "no_training": (
        "No training records found for this participant.",
        "រកមិនឃើញប្រវត្តិបណ្ដុះបណ្ដាលសម្រាប់អ្នកចូលរួមរូបនេះទេ។",
    ),
    "no_certificate": (
        "No certificate pickup records found for this participant.",
        "រកមិនឃើញប្រវត្តិវិញ្ញាបនបត្រសម្រាប់អ្នកចូលរួមរូបនេះទេ។",
    ),
    "picked_up": ("Picked up", "បានទទួល"),
    "not_picked_up": ("Not picked up", "មិនទាន់ទទួល"),
    "not_applicable": ("-", "-"),
    "help": (
        "Commands:\n"
        "/start - Start / restart the bot\n"
        "/view - View your CPD history\n"
        "/myid - Show your Telegram ID\n"
        "/unlink - Unlink your account\n"
        "/help - Show this help\n"
        "/cancel - Cancel current action",
        "ពាក្យបញ្ជា៖\n"
        "/start - ចាប់ផ្ដើម / ចាប់ផ្ដើមឡើងវិញ\n"
        "/view - មើលប្រវត្តិ CPD\n"
        "/myid - បង្ហាញ Telegram ID របស់អ្នក\n"
        "/unlink - ផ្ដាច់ការភ្ជាប់គណនី\n"
        "/help - បង្ហាញជំនួយ\n"
        "/cancel - បោះបង់សកម្មភាពបច្ចុប្បន្ន",
    ),
    "your_telegram_id": (
        "Your Telegram ID is: <code>{tid}</code>\nShare this with the admin if you have an account linking problem.",
        "Telegram ID របស់អ្នកគឺ: <code>{tid}</code>\nចែករំលែកនេះជាមួយអ្នកគ្រប់គ្រង ប្រសិនបើអ្នកមានបញ្ហាភ្ជាប់គណនី។",
    ),
    "account_unlinked": (
        "Your account has been unlinked. Use /start to verify again.",
        "គណនីរបស់អ្នកត្រូវបានផ្ដាច់។ ប្រើ /start ដើម្បីផ្ទៀងផ្ទាត់ម្ដងទៀត។",
    ),
    "not_linked": (
        "Your account is not linked yet. Use /start to get started.",
        "គណនីរបស់អ្នកមិនទាន់ភ្ជាប់ទេ។ ប្រើ /start ដើម្បីចាប់ផ្ដើម។",
    ),
    "admin_only": (
        "⛔ This command is for admins only.",
        "⛔ ពាក្យបញ្ជានេះសម្រាប់តែអ្នកគ្រប់គ្រងប៉ុណ្ណោះ។",
    ),
    "admin_help": (
        "<b>🔧 Admin Commands:</b>\n"
        "/admin_list — List all linked accounts\n"
        "/admin_link &lt;TelegramID&gt; &lt;Name&gt; — Link an ID to a participant\n"
        "/admin_unlink &lt;TelegramID or Name&gt; — Unlink an account\n"
        "/admin_view &lt;Name&gt; — View a participant's CPD history",
        "<b>🔧 ពាក្យបញ្ជាអ្នកគ្រប់គ្រង:</b>\n"
        "/admin_list — បញ្ជីគណនីភ្ជាប់ទាំងអស់\n"
        "/admin_link &lt;TelegramID&gt; &lt;ឈ្មោះ&gt; — ភ្ជាប់ ID ទៅនឹងអ្នកចូលរួម\n"
        "/admin_unlink &lt;TelegramID ឬ ឈ្មោះ&gt; — ផ្ដាច់គណនី\n"
        "/admin_view &lt;ឈ្មោះ&gt; — មើលប្រវត្តិ CPD អ្នកចូលរួម",
    ),
    "search_again": ("Search another name", "ស្វែងរកឈ្មោះផ្សេងទៀត"),
    "done": (
        "Thank you! You can start a new search any time with /start.",
        "សូមអរគុណ! អ្នកអាចចាប់ផ្ដើមការស្វែងរកថ្មីនៅពេលណាក៏បានដោយផ្ញើ /start។",
    ),
    "menu_title": ("What would you like to see?", "តើអ្នកចង់មើលអ្វី?"),
    "error": (
        "Sorry, something went wrong. Please try again later.",
        "សូមទោស មានបញ្ហាអ្វីមួយកើតឡើង។ សូមព្យាយាមម្ដងទៀតនៅពេលក្រោយ។",
    ),
    "loading_error": (
        "The CPD data files could not be loaded. Please contact the administrator.",
        "មិនអាចផ្ទុកឯកសារទិន្នន័យ CPD បានទេ។ សូមទាក់ទងអ្នកគ្រប់គ្រង។",
    ),
    "further_info": (
        "For further information, please contact CPD officer Eng Sophanith (+855 98 448 619).",
        "សម្រាប់ព័ត៌មានបន្ថែម សូមទាក់ទង លោក អៀង សុផានិត (Telegram: +855 98 448 619)។",
    ),
}


def t(key: str) -> str:
    pair = TRANSLATIONS[key]
    return pair[1]


def inline(key: str, **kwargs: object) -> str:
    return t(key).format(**kwargs)


def fmt(key: str, **kwargs: object) -> str:
    return t(key).format(**kwargs)


# -------------------------------------------------------------------- records
@dataclass
class Course:
    course_id: str = ""
    title: str = ""
    date: str = ""
    cpd_points: str = ""
    link: str = ""
    status: str = ""


@dataclass
class Participant:
    participant_id: str = ""
    name: str = ""
    khmer_name: str = ""
    profession: str = ""
    department: str = ""
    email: str = ""
    phone: str = ""


@dataclass
class Training:
    training_id: str = ""
    participant_id: str = ""
    participant_name: str = ""
    title: str = ""
    date: str = ""
    organizer: str = ""
    cpd_points: str = ""
    hours: str = ""
    status: str = ""


@dataclass
class Certificate:
    certificate_id: str = ""
    participant_id: str = ""
    participant_name: str = ""
    khmer_name: str = ""
    training_title: str = ""
    certificate_number: str = ""
    issued_date: str = ""
    picked_up: bool = False
    pickup_date: str = ""
    pickup_by: str = ""


def _record_from(cls, d: dict):
    allowed = {f.name for f in cls.__dataclass_fields__.values()}
    return cls(**{k: v for k, v in (d or {}).items() if k in allowed})


# ----------------------------------------------------------------------- data
class CpdData:
    """JSON-backed mirror of cpd.data_loader.CpdData."""

    def __init__(self, data: dict):
        self.participants: list[Participant] = [
            _record_from(Participant, d) for d in data.get("participants", [])
        ]
        self.trainings: list[Training] = [
            _record_from(Training, d) for d in data.get("trainings", [])
        ]
        self.certificates: list[Certificate] = [
            _record_from(Certificate, d) for d in data.get("certificates", [])
        ]
        self.courses: list[Course] = [
            _record_from(Course, d) for d in data.get("courses", [])
        ]
        self._trainings_by_id: dict[str, list[Training]] = {}
        self._trainings_by_name: dict[str, list[Training]] = {}
        self._certs_by_id: dict[str, list[Certificate]] = {}
        self._certs_by_name: dict[str, list[Certificate]] = {}
        self._rebuild_indices()

    def _rebuild_indices(self) -> None:
        for t in self.trainings:
            if t.participant_id:
                self._trainings_by_id.setdefault(t.participant_id, []).append(t)
            if t.participant_name:
                self._trainings_by_name.setdefault(t.participant_name.lower(), []).append(t)
        for c in self.certificates:
            if c.participant_id:
                self._certs_by_id.setdefault(c.participant_id, []).append(c)
            if c.participant_name:
                self._certs_by_name.setdefault(c.participant_name.lower(), []).append(c)
            if c.khmer_name:
                self._certs_by_name.setdefault(c.khmer_name.lower(), []).append(c)

    def all_names(self) -> list[str]:
        names = [p.name for p in self.participants if p.name]
        names += [p.khmer_name for p in self.participants if p.khmer_name]
        names += [t.participant_name for t in self.trainings if t.participant_name]
        names += [c.participant_name for c in self.certificates if c.participant_name]
        names += [c.khmer_name for c in self.certificates if c.khmer_name]
        return sorted(set(names))

    def find_participant(self, identifier: str) -> Participant | None:
        for p in self.participants:
            if p.participant_id and p.participant_id == identifier:
                return p
            if p.name and p.name.lower() == identifier.lower():
                return p
            if p.khmer_name and p.khmer_name == identifier:
                return p
        return None

    def trainings_for(self, participant_id: str = "", participant_name: str = "", khmer_name: str = "") -> list[Training]:
        out: list[Training] = []
        seen: set[int] = set()
        if participant_id:
            for t in self._trainings_by_id.get(participant_id, []):
                out.append(t)
                seen.add(id(t))
        for name in [n for n in (participant_name, khmer_name) if n]:
            for t in self._trainings_by_name.get(name.lower(), []):
                if id(t) not in seen:
                    out.append(t)
                    seen.add(id(t))
            norm_name = normalize_name(name)
            if not norm_name:
                continue
            for t in self.trainings:
                if id(t) not in seen:
                    t_name = normalize_name(t.participant_name or "")
                    if norm_name and (norm_name == t_name or norm_name in t_name or t_name in norm_name):
                        out.append(t)
                        seen.add(id(t))
        return out

    def certificates_for(self, participant_id: str = "", participant_name: str = "", khmer_name: str = "") -> list[Certificate]:
        out: list[Certificate] = []
        seen: set[int] = set()
        if participant_id:
            for c in self._certs_by_id.get(participant_id, []):
                out.append(c)
                seen.add(id(c))
        for name in [n for n in (participant_name, khmer_name) if n]:
            for c in self._certs_by_name.get(name.lower(), []):
                if id(c) not in seen:
                    out.append(c)
                    seen.add(id(c))
            norm_name = normalize_name(name)
            if not norm_name:
                continue
            for c in self.certificates:
                if id(c) not in seen:
                    c_name = normalize_name(c.participant_name or "")
                    c_khmer = normalize_name(c.khmer_name or "")
                    if norm_name and (norm_name == c_name or norm_name == c_khmer or
                                      norm_name in c_name or norm_name in c_khmer):
                        out.append(c)
                        seen.add(id(c))
        return out


# -------------------------------------------------------------------- storage
LINKS_KEY = "links"
DATA_KEY = "data"
DATA_REFRESH_SECONDS = 300

_DATA: CpdData | None = None
_DATA_TS = 0.0


async def _kv_get(env, key: str) -> str | None:
    raw = await env.CPD_KV.get(key)
    if raw is None:
        return None
    return str(raw)


async def _kv_put(env, key: str, value: str) -> None:
    await env.CPD_KV.put(key, value)


async def get_linked_name(env, telegram_id: int) -> str | None:
    raw = await _kv_get(env, LINKS_KEY)
    if not raw:
        return None
    try:
        return json.loads(raw).get(str(telegram_id))
    except Exception:
        return None


async def link_account(env, telegram_id: int, name: str) -> None:
    raw = await _kv_get(env, LINKS_KEY)
    try:
        links = json.loads(raw) if raw else {}
    except Exception:
        links = {}
    links[str(telegram_id)] = name
    await _kv_put(env, LINKS_KEY, json.dumps(links, ensure_ascii=False))


async def unlink_account(env, telegram_id: int) -> None:
    raw = await _kv_get(env, LINKS_KEY)
    if not raw:
        return
    try:
        links = json.loads(raw)
    except Exception:
        return
    if str(telegram_id) in links:
        del links[str(telegram_id)]
        await _kv_put(env, LINKS_KEY, json.dumps(links, ensure_ascii=False))


async def list_all_links(env) -> dict[str, str]:
    raw = await _kv_get(env, LINKS_KEY)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


async def find_telegram_id_by_name(env, name: str) -> str | None:
    links = await list_all_links(env)
    name_lower = name.strip().lower()
    for tid, pname in links.items():
        if pname.strip().lower() == name_lower:
            return tid
    return None


async def admin_unlink_by_name(env, name: str) -> bool:
    tid = await find_telegram_id_by_name(env, name)
    if tid is None:
        return False
    await unlink_account(env, int(tid))
    return True


async def get_data(env) -> CpdData:
    global _DATA, _DATA_TS
    now = time.time()
    if _DATA is not None and now - _DATA_TS < DATA_REFRESH_SECONDS:
        return _DATA
    raw = await _kv_get(env, DATA_KEY)
    if not raw:
        raise RuntimeError("CPD data is not uploaded to KV yet (key 'data')")
    _DATA = CpdData(json.loads(raw))
    _DATA_TS = now
    return _DATA


# --------------------------------------------------------------------- search
KHMER_DIGITS = str.maketrans("០១២៣៤៥៦៧៨៩", "0123456789")
AUTO_SELECT_MARGIN = 0.25


def _norm_phone(value: object) -> str:
    import re

    s = str(value or "").translate(KHMER_DIGITS)
    return "".join(ch for ch in s if ch.isdigit())


def _phone_tokens(value: object) -> list[str]:
    import re

    s = str(value or "").translate(KHMER_DIGITS)
    return re.findall(r"\d{8,11}", s)


def normalize_name(name: str) -> str:
    name = name.replace("\u200b", "").replace("\u200c", "")
    text = unicodedata.normalize("NFKD", name).strip().lower()
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.split())


def _score(candidate: str, query: str) -> tuple[float, int]:
    c = normalize_name(candidate)
    q = normalize_name(query)
    if not q or not c:
        return 0.0, 0
    if c == q:
        return 1.5, len(q)
    if c in q or q in c:
        return 1.2 + 0.01 * min(len(q), len(c)), len(c)
    ratio = SequenceMatcher(None, c, q).ratio()
    return max(0.0, ratio), len(c)


def rank_candidates(query: str, candidates: list[str], limit: int = 6) -> list[str]:
    q = normalize_name(query)
    if not q:
        return []
    scored = []
    for cand in candidates:
        base, bonus = _score(cand, q)
        if base >= 0.55:
            scored.append((base + 0.0001 * bonus, cand))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [name for _, name in scored[:limit]]


def exact_participant(participants: list[Participant], name: str) -> Participant | None:
    q = normalize_name(name)
    if not q:
        return None
    for p in participants:
        if p.name and normalize_name(p.name) == q:
            return p
        if p.khmer_name and normalize_name(p.khmer_name) == q:
            return p
    return None


def resolve_participant(query: str, names: list[str], participants: list[Participant]):
    ranked = rank_candidates(query, names)
    if not ranked:
        return None, [], False
    best_name = ranked[0]
    if len(ranked) == 1:
        return exact_participant(participants, best_name) or Participant(name=best_name), ranked, True
    best_score, _ = _score(best_name, query)
    runner_score, _ = _score(ranked[1], query) if len(ranked) > 1 else (0.0, 0)
    if best_score - runner_score >= AUTO_SELECT_MARGIN:
        return exact_participant(participants, best_name) or Participant(name=best_name), ranked, True
    return None, ranked, False


def find_participant_by_secret(participants: list[Participant], secret: str) -> Participant | None:
    s = secret.strip().lower()
    if not s:
        return None
    for p in participants:
        if p.participant_id and p.participant_id.strip().lower() == s:
            return p
    s_phone = _norm_phone(s)
    if s_phone:
        for p in participants:
            if s_phone in _phone_tokens(p.phone):
                return p
    return None


def search_all_fields(query: str, data: CpdData) -> tuple[Participant | None, list[str]]:
    q = query.strip().lower()
    if not q:
        return None, []
    p_exact = find_participant_by_secret(data.participants, query)
    if p_exact:
        return p_exact, []
    matches = []
    q_norm = normalize_name(query)
    for p in data.participants:
        fields = [p.participant_id, p.name, p.khmer_name, p.profession, p.department, p.email, p.phone]
        text_to_search = " ".join(str(f) for f in fields if f).lower()
        norm_text = normalize_name(text_to_search)
        if q in text_to_search or (q_norm and q_norm in norm_text):
            matches.append(p.name or p.khmer_name or p.participant_id)
    matches = list(dict.fromkeys(m for m in matches if m))
    if not matches:
        chosen, shortlist, _auto = resolve_participant(query, data.all_names(), data.participants)
        if chosen:
            return chosen, []
        return None, shortlist
    if len(matches) == 1:
        p_name = matches[0]
        p_resolved = exact_participant(data.participants, p_name)
        if p_resolved:
            return p_resolved, []
        return Participant(name=p_name), []
    return None, matches[:10]


# ------------------------------------------------------------------ formatter
EMPTY = "—"


def _esc(value: str) -> str:
    return html.escape(value or "", quote=False)


def _row(title: str, value: str) -> str:
    value = value or EMPTY
    return f"<b>{_esc(title)}:</b> {_esc(value)}"


def _date(value: str) -> str:
    if not value:
        return EMPTY
    parts = [p.strip().split(" ")[0] for p in value.split(",") if p.strip()]
    return ", ".join(p for p in parts if p)


def participant_header(p: Participant) -> str:
    lines = [f"<b>{_esc(p.name)}</b>"]
    if p.khmer_name and p.khmer_name != p.name:
        lines.append(_esc(p.khmer_name))
    details = [d for d in (p.profession, p.department) if d]
    if details:
        lines.append(" | ".join(_esc(d) for d in details))
    if p.participant_id:
        lines.append(f'ID: <code>{_esc(p.participant_id)}</code>')
    return NL.join(lines)


def _training_line(tr: Training) -> str:
    bits = []
    date_str = _date(tr.date) if tr.date and tr.date.lower() not in ("nan", "") else "No date"
    bits.append(f"<b>{_esc(date_str)}</b>")
    if tr.title:
        bits.append(_esc(tr.title))
    if tr.organizer:
        bits.append(f"({_esc(tr.organizer)})")
    if tr.cpd_points:
        bits.append(f"<b>{_esc(tr.cpd_points)} ពិន្ទុ</b>")
    if tr.hours:
        bits.append(f"{_esc(tr.hours)}ម៉ោង")
    if not bits:
        return ""
    return "• " + " · ".join(bits)


def training_lines(trainings: list[Training]) -> str:
    sorted_trainings = sorted(trainings, key=lambda tr: tr.date or "", reverse=True)
    lines = [_training_line(tr) for tr in sorted_trainings]
    return NL.join(line for line in lines if line)


def _certificate_line(c: Certificate, matched_training: Training | None = None) -> str:
    status = inline("picked_up") if c.picked_up else inline("not_picked_up")
    bits = [f"<b>{_esc(status)}</b>"]
    if matched_training and matched_training.title:
        bits.append(_esc(matched_training.title))
        if matched_training.organizer:
            bits.append(f"({_esc(matched_training.organizer)})")
    elif c.training_title:
        bits.append(_esc(c.training_title))
    if c.certificate_number:
        bits.append(f"លេខ {_esc(c.certificate_number)}")
    if c.issued_date:
        bits.append(f"{_esc(_date(c.issued_date))}")
    extra = ""
    if c.picked_up and c.pickup_date:
        extra = f"បានទទួលថ្ងៃទី {_esc(_date(c.pickup_date))}"
        pickup_by = c.pickup_by.strip() if c.pickup_by else ""
        if pickup_by and pickup_by.lower() not in ("nan", "-", "n/a"):
            extra += f" ដោយ {_esc(pickup_by)}"
    if extra:
        return f"• {extra}"
    line = "• " + " · ".join(bits)
    return line


def _match_training_for_cert(c: Certificate, trainings: list[Training]) -> Training | None:
    study_date = c.training_title.strip() if c.training_title else ""
    if not study_date:
        return None
    for tr in trainings:
        if tr.date and tr.date.startswith(study_date):
            return tr
        if study_date and tr.date and tr.date == study_date:
            return tr
    return None


def certificate_lines(certificates: list[Certificate], trainings: list[Training] | None = None) -> str:
    certs = sorted(certificates, key=lambda c: c.training_title or "", reverse=True)
    tr_list = list(trainings) if trainings else []
    lines = []
    for c in certs:
        matched = _match_training_for_cert(c, tr_list)
        lines.append(_certificate_line(c, matched))
    return NL.join(lines)


def _cert_status_for_trainings(trainings: list[Training], certificates: list[Certificate]) -> list[str]:
    if not certificates:
        return []
    lines = []
    for c in sorted(certificates, key=lambda c: c.training_title or "", reverse=True):
        study_date = c.training_title.strip() if c.training_title else ""
        matched_tr = None
        for tr in trainings:
            if tr.date and study_date and tr.date.startswith(study_date):
                matched_tr = tr
                break
        title_bits = []
        if matched_tr:
            if matched_tr.title:
                title_bits.append(_esc(matched_tr.title))
            if matched_tr.organizer:
                title_bits.append(f"({_esc(matched_tr.organizer)})")
        elif study_date:
            title_bits.append(_esc(study_date))
        title_str = " · ".join(title_bits) if title_bits else ""
        status = inline("picked_up") if c.picked_up else inline("not_picked_up")
        if c.picked_up and c.pickup_date:
            extra = f"បានទទួលថ្ងៃទី {_esc(_date(c.pickup_date))}"
            pb = c.pickup_by.strip() if c.pickup_by else ""
            if pb and pb.lower() not in ("nan", "-", "n/a"):
                extra += f" ដោយ {_esc(pb)}"
            lines.append(f"• {extra}")
        else:
            line = f"• <b>{_esc(status)}</b>"
            if title_str:
                line += f" · {title_str}"
            lines.append(line)
    return lines


def section_heading(heading_key: str) -> str:
    return f"<b>{_esc(inline(heading_key))}</b>"


def _counts(trainings: list[Training], certificates: list[Certificate]) -> list[str]:
    total_points = 0.0
    for tr in trainings:
        try:
            total_points += float(tr.cpd_points) if tr.cpd_points else 0.0
        except ValueError:
            pass
    picked = sum(1 for c in certificates if c.picked_up)
    lines = [
        _row("ចំនួនវគ្គបណ្ដុះបណ្ដាលសរុប", str(len(trainings))),
        _row("ពិន្ទុ CPD សរុប", f"{total_points:g}" if total_points else "0"),
    ]
    if trainings:
        total_expected = len(trainings)
        lines.append(_row("វិញ្ញាបនបត្រដែលបានទទួល", f"{picked} / {total_expected}"))
        lines.append(_row("វិញ្ញាបនបត្រមិនទាន់ទទួល", str(total_expected - picked)))
    return lines


def summary_sections(p: Participant, trainings: list[Training], certificates: list[Certificate]) -> list[str]:
    head = [participant_header(p), ""] + _counts(trainings, certificates)
    sections: list[str] = [NL.join(head)]
    if trainings:
        sections.append(NL + section_heading("section_training") + NL + training_lines(trainings))
    else:
        sections.append(NL + section_heading("section_training") + NL + t("no_training"))
    cert_lines = _cert_status_for_trainings(trainings, certificates)
    cert_text = NL.join(cert_lines) if cert_lines else t("no_certificate")
    sections.append(NL + section_heading("section_certificate") + NL + cert_text + NL + NL + t("further_info"))
    return sections


def summary_report(p: Participant, trainings: list[Training], certificates: list[Certificate]) -> str:
    return NL.join(summary_sections(p, trainings, certificates))


def training_report(participant_name: str, trainings: list[Training]) -> str:
    if not trainings:
        return f"<b>{_esc(participant_name)}</b>{NL}{t('no_training')}{NL}{NL}{t('further_info')}"
    return (
        f"<b>{_esc(participant_name)}</b> — {_esc(inline('section_training'))}"
        f"{NL}{training_lines(trainings)}{NL}{NL}{t('further_info')}"
    )


def certificate_report(participant_name: str, certificates: list[Certificate]) -> str:
    if not certificates:
        return f"<b>{_esc(participant_name)}</b>{NL}{t('no_certificate')}{NL}{NL}{t('further_info')}"
    return (
        f"<b>{_esc(participant_name)}</b> — {_esc(inline('section_certificate'))}"
        f"{NL}{certificate_lines(certificates)}{NL}{NL}{t('further_info')}"
    )


# ------------------------------------------------------------------ keyboards
def start_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "📋 ចុះឈ្មោះវគ្គបណ្តុះបណ្តាល (Register for Course)", "callback_data": "start|register"},
                {"text": "📊 មើលប្រវត្តិ CPD (View CPD History)", "callback_data": "start|view_cpd"},
            ]
        ]
    }


def menu_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "សង្ខេប", "callback_data": "menu|summary"},
                {"text": "បណ្ដុះបណ្ដាល", "callback_data": "menu|training"},
                {"text": "វិញ្ញាបនបត្រ", "callback_data": "menu|certificate"},
            ],
            [
                {"text": "ស្វែងរកផ្សេង", "callback_data": "menu|search"},
                {"text": "រួចរាល់", "callback_data": "menu|done"},
            ],
        ]
    }


# ------------------------------------------------------------ Telegram helpers
def _api_base(env) -> str:
    return f"https://api.telegram.org/bot{env.TELEGRAM_BOT_TOKEN}"


async def _tg(env, method: str, payload: dict) -> dict:
    resp = await fetch(f"{_api_base(env)}/{method}", {
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    })
    text = await resp.text()
    try:
        return json.loads(text) if text else {}
    except Exception:
        return {}


def _log(env, msg: str) -> None:
    try:
        console.log(f"[cpd-track] {msg}")
    except Exception:
        pass


async def safe_reply_html(env, chat_id: int, text: str, markup: dict | None = None, disable_web_page_preview: bool | None = None) -> None:
    try:
        payload: dict = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if markup is not None:
            payload["reply_markup"] = markup
        if disable_web_page_preview is not None:
            payload["disable_web_page_preview"] = disable_web_page_preview
        await _tg(env, "sendMessage", payload)
    except Exception as exc:
        _log(env, f"send failed: {exc}")
        try:
            await _tg(env, "sendMessage", {"chat_id": chat_id, "text": t("error")})
        except Exception:
            pass


async def edit_message(env, chat_id: int, message_id: int, text: str, markup: dict | None = None, disable_web_page_preview: bool | None = None) -> None:
    payload: dict = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"}
    if markup is not None:
        payload["reply_markup"] = markup
    if disable_web_page_preview is not None:
        payload["disable_web_page_preview"] = disable_web_page_preview
    await _tg(env, "editMessageText", payload)


async def delete_message(env, chat_id: int, message_id: int) -> None:
    await _tg(env, "deleteMessage", {"chat_id": chat_id, "message_id": message_id})


async def answer_callback(env, callback_query_id: str, text: str | None = None) -> None:
    payload: dict = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    await _tg(env, "answerCallbackQuery", payload)


# --------------------------------------------------------------- bot handlers
async def show_summary(env, chat_id: int, message_id: int | None, name: str, edit: bool = False) -> None:
    data = await get_data(env)
    participant = _resolve_for_name(data, name)
    trainings = data.trainings_for(participant.participant_id, participant.name, participant.khmer_name)
    certificates = data.certificates_for(participant.participant_id, participant.name, participant.khmer_name)
    sections = summary_sections(participant, trainings, certificates)
    text = NL.join(sections)
    if edit and message_id is not None:
        try:
            await edit_message(env, chat_id, message_id, text, markup=menu_keyboard())
            return
        except Exception:
            pass
    if len(text) <= 3800:
        await safe_reply_html(env, chat_id, text, markup=menu_keyboard())
    else:
        for idx, section in enumerate(sections):
            markup = menu_keyboard() if idx == len(sections) - 1 else None
            await safe_reply_html(env, chat_id, section, markup=markup)


def _resolve_for_name(data: CpdData, name: str) -> Participant:
    participant = exact_participant(data.participants, name)
    if participant is not None:
        return participant
    norm_query = normalize_name(name)
    for t in data.trainings:
        if normalize_name(t.participant_name) == norm_query:
            return Participant(participant_id=t.participant_id, name=name)
    for c in data.certificates:
        if normalize_name(c.participant_name) == norm_query or normalize_name(c.khmer_name) == norm_query:
            return Participant(participant_id=c.participant_id, name=c.participant_name or name, khmer_name=c.khmer_name)
    return Participant(participant_id="", name=name)


async def handle_verification(env, chat_id: int, user_id: int, query: str) -> None:
    try:
        data = await get_data(env)
    except Exception:
        await safe_reply_html(env, chat_id, t("loading_error"))
        return
    if not query.strip():
        await safe_reply_html(env, chat_id, t("ask_verification"))
        return
    participant, shortlist = search_all_fields(query, data)
    if participant is None and not shortlist:
        await safe_reply_html(env, chat_id, t("not_found_verification"))
        return
    if participant is not None:
        await link_account(env, user_id, participant.name)
        await safe_reply_html(env, chat_id, fmt("account_linked", name=html.escape(participant.name)))
        await show_summary(env, chat_id, None, participant.name)
        return
    buttons = [[{"text": name, "callback_data": f"pick|{name}"}] for name in shortlist]
    await safe_reply_html(env, chat_id, fmt("multiple_matches", count=len(shortlist)), markup={"inline_keyboard": buttons})


async def on_message_text(env, chat_id: int, user_id: int, text: str) -> None:
    linked = await get_linked_name(env, user_id)
    if linked:
        await show_summary(env, chat_id, None, linked)
        return
    await handle_verification(env, chat_id, user_id, text)


def _is_admin(user_id: int, env) -> bool:
    raw = getattr(env, "ADMIN_IDS", "") or ""
    admin_ids = {int(x) for x in str(raw).split(",") if x.strip().isdigit()}
    return user_id in admin_ids


async def handle_command(env, chat_id: int, user_id: int, text: str) -> None:
    parts = text.split()
    cmd = parts[0].split("@")[0].lower()
    args = parts[1:]

    if cmd == "/start":
        await safe_reply_html(env, chat_id, t("welcome"), markup=start_keyboard())
    elif cmd == "/view":
        linked = await get_linked_name(env, user_id)
        if linked:
            await show_summary(env, chat_id, None, linked)
            return
        query = " ".join(args).strip()
        if not query:
            await safe_reply_html(env, chat_id, t("ask_verification"))
        else:
            await handle_verification(env, chat_id, user_id, query)
    elif cmd == "/help":
        msg = t("help")
        if _is_admin(user_id, env):
            msg += "\n\n" + t("admin_help")
        await safe_reply_html(env, chat_id, msg)
    elif cmd == "/cancel":
        await safe_reply_html(env, chat_id, t("cancel"))
    elif cmd == "/myid":
        await safe_reply_html(env, chat_id, fmt("your_telegram_id", tid=user_id))
    elif cmd == "/unlink":
        name = await get_linked_name(env, user_id)
        if not name:
            await safe_reply_html(env, chat_id, t("not_linked"))
            return
        await unlink_account(env, user_id)
        await safe_reply_html(env, chat_id, t("account_unlinked"))
    elif cmd == "/admin_list":
        if not _is_admin(user_id, env):
            await safe_reply_html(env, chat_id, t("admin_only"))
            return
        links = await list_all_links(env)
        if not links:
            await safe_reply_html(env, chat_id, "No accounts linked yet.")
            return
        lines = ["<b>🔗 Linked accounts:</b>"]
        for tid, name in sorted(links.items(), key=lambda x: x[1]):
            lines.append(f"• <code>{tid}</code> → {html.escape(name)}")
        await safe_reply_html(env, chat_id, "\n".join(lines))
    elif cmd == "/admin_link":
        if not _is_admin(user_id, env):
            await safe_reply_html(env, chat_id, t("admin_only"))
            return
        if len(args) < 2 or not args[0].isdigit():
            await safe_reply_html(env, chat_id,
                "Usage: /admin_link &lt;TelegramID&gt; &lt;Full Name&gt;\n"
                "Example: /admin_link 123456789 KY Kimhuy")
            return
        tid = int(args[0])
        name = " ".join(args[1:])
        await link_account(env, tid, name)
        await safe_reply_html(env, chat_id, f"✅ Linked <code>{tid}</code> → <b>{html.escape(name)}</b>")
    elif cmd == "/admin_unlink":
        if not _is_admin(user_id, env):
            await safe_reply_html(env, chat_id, t("admin_only"))
            return
        if not args:
            await safe_reply_html(env, chat_id,
                "Usage: /admin_unlink &lt;TelegramID or Full Name&gt;\n"
                "Example: /admin_unlink 123456789\n"
                "Example: /admin_unlink KY Kimhuy")
            return
        query = " ".join(args)
        if query.isdigit():
            await unlink_account(env, int(query))
            await safe_reply_html(env, chat_id, f"✅ Unlinked Telegram ID <code>{query}</code>")
        else:
            found = await admin_unlink_by_name(env, query)
            if found:
                await safe_reply_html(env, chat_id, f"✅ Unlinked account for <b>{html.escape(query)}</b>")
            else:
                await safe_reply_html(env, chat_id, f"❌ No linked account found for <b>{html.escape(query)}</b>")
    elif cmd == "/admin_view":
        if not _is_admin(user_id, env):
            await safe_reply_html(env, chat_id, t("admin_only"))
            return
        name = " ".join(args).strip()
        if not name:
            await safe_reply_html(env, chat_id,
                "Usage: /admin_view &lt;Full Name&gt;\n"
                "Example: /admin_view KY Kimhuy")
            return
        await show_summary(env, chat_id, None, name)


async def on_start_option(env, chat_id: int, message_id: int, user_id: int, data: str) -> None:
    action = data.split("|")[1]
    if action == "view_cpd":
        linked = await get_linked_name(env, user_id)
        if linked:
            await show_summary(env, chat_id, message_id, linked, edit=True)
        else:
            await edit_message(env, chat_id, message_id, t("ask_verification"))
    elif action == "register":
        try:
            cpd = await get_data(env)
        except Exception:
            await edit_message(env, chat_id, message_id, t("loading_error"))
            return
        link = getattr(env, "COURSE_REGISTRATION_LINK", "") or ""
        open_courses = [c for c in cpd.courses if c.status.strip().lower() not in ("done", "completed", "ចប់")]
        if not open_courses:
            text = "គ្មានវគ្គបណ្តុះបណ្តាលសម្រាប់ការចុះឈ្មោះទេនៅពេលនេះ។ (No courses available for registration at this time.)"
        else:
            text = "<b>📚 វគ្គបណ្តុះបណ្តាលដែលបើកឱ្យចុះឈ្មោះ (Available Courses):</b>\n\n"
            for c in open_courses:
                text += f"• <b>{html.escape(c.title)}</b>\n"
                text += f"  🗓️ កាលបរិច្ឆេទ (Date): {html.escape(c.date)}\n"
                text += f"  ⭐ ពិន្ទុ CPD (CPD Points): {html.escape(c.cpd_points)}\n\n"
            if link:
                text += (f"<b>🔗 តំណភ្ជាប់ចុះឈ្មោះ (Register Link):</b>\n"
                         f"<a href='{link}'>{link}</a>\n")
            text += NL + NL + t("further_info")
        await edit_message(env, chat_id, message_id, text, disable_web_page_preview=True)


async def on_pick(env, chat_id: int, user_id: int, data: str) -> None:
    name = data.split("|", 1)[1]
    await link_account(env, user_id, name)
    await safe_reply_html(env, chat_id, fmt("account_linked", name=html.escape(name)))
    await show_summary(env, chat_id, None, name)


async def on_menu(env, chat_id: int, message_id: int, user_id: int, data: str) -> None:
    action = data.split("|", 1)[1]
    try:
        cpd = await get_data(env)
    except Exception:
        await edit_message(env, chat_id, message_id, t("loading_error"))
        return
    name = await get_linked_name(env, user_id)
    if not name:
        await edit_message(env, chat_id, message_id, t("ask_name"))
        return
    participant = _resolve_for_name(cpd, name)
    trainings = cpd.trainings_for(participant.participant_id, participant.name, participant.khmer_name)
    certificates = cpd.certificates_for(participant.participant_id, participant.name, participant.khmer_name)

    if action == "summary":
        await edit_message(env, chat_id, message_id, summary_report(participant, trainings, certificates), markup=menu_keyboard())
    elif action == "training":
        await edit_message(env, chat_id, message_id, training_report(participant.name, trainings), markup=menu_keyboard())
    elif action == "certificate":
        await edit_message(env, chat_id, message_id, certificate_report(participant.name, certificates), markup=menu_keyboard())
    elif action == "search":
        await unlink_account(env, user_id)
        await edit_message(env, chat_id, message_id, t("ask_verification"))
    elif action == "done":
        try:
            await delete_message(env, chat_id, message_id)
        except Exception:
            await edit_message(env, chat_id, message_id, t("done"))


async def handle_callback(env, query: dict) -> None:
    callback_id = query.get("id", "")
    user_id = query.get("from", {}).get("id", 0)
    message = query.get("message", {})
    chat_id = message.get("chat", {}).get("id", 0)
    message_id = message.get("message_id")
    data = query.get("data", "")
    try:
        await answer_callback(env, callback_id)
    except Exception:
        pass
    if not chat_id or message_id is None:
        return
    if data.startswith("start|"):
        await on_start_option(env, chat_id, message_id, user_id, data)
    elif data.startswith("pick|"):
        await on_pick(env, chat_id, user_id, data)
    elif data.startswith("menu|"):
        await on_menu(env, chat_id, message_id, user_id, data)


async def handle_update(env, update: dict) -> None:
    if "callback_query" in update:
        await handle_callback(env, update["callback_query"])
    elif "message" in update:
        msg = update["message"]
        chat_id = msg.get("chat", {}).get("id", 0)
        user_id = msg.get("from", {}).get("id", 0)
        text = msg.get("text", "")
        if text and text.startswith("/"):
            await handle_command(env, chat_id, user_id, text)
        else:
            await on_message_text(env, chat_id, user_id, text)


# -------------------------------------------------------------------- worker
if IS_WORKER:
    class Default(WorkerEntrypoint):  # type: ignore[misc]
        async def fetch(self, request):
            if request.method == "GET":
                return Response("ok")
            try:
                raw = await request.text()
            except Exception:
                raw = ""
            if raw:
                try:
                    update = json.loads(raw)
                except Exception:
                    update = {}
                if isinstance(update, dict):
                    try:
                        await handle_update(self.env, update)
                    except Exception as exc:
                        _log(self.env, f"handler error: {exc}")
            return Response("ok")