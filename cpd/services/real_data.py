"""Adapter for the real Google-Forms Excel exports used by the CPD system.

Two files sit in ``data/``:

1. Registration form ("ការចុះឈ្មោះប្រធានបទ ..." Responses)
   One row per participant. Stores their name (Khmer + Latin), pharmacy
   council (PCC) number, phone, education details, and the training topic(s)
   they registered for. A topic column with a value other than
   "មិនជ្រើសរើស" (not selected) means the person registered for that
   topic, and the value describes the session (day/time slot).

2. Certificate pickup form ("ទម្រង់បែបបទបំពេញ ដកវិញ្ញាបនបត្រ ...")
   One row per certificate collection event: pharmacist name (Khmer +
   English), the actual pickup date, whether collected in person or by a
   proxy, delivery-team confirmation, and the study date(s).

Both files are auto-detected by column keywords, so downloading fresh Google
Form responses into ``data/`` "just works" without code changes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from cpd.services.data_loader import Certificate, Participant, Training, _norm
from cpd.services.search import normalize_name

KHMER_DIGITS = str.maketrans("០១២៣៤៥៦៧៨៩", "0123456789")

KHMER_MONTHS = {
    "មករា": 1, "កុម្ភៈ": 2, "មិនា": 3, "មេសា": 4,
    "ឧសភា": 5, "មិថុនា": 6, "កក្កដា": 7, "សីហា": 8,
    "កញ្ញា": 9, "តុលា": 10, "វិច្ឆិកា": 11, "ធ្នូ": 12,
}

NOT_SELECTED = "មិនជ្រើសរើស"

# ------------------------------------------------------------------ helpers
def _latinize(text: str) -> str:
    return str(text).translate(KHMER_DIGITS)


def _norm_phone(value) -> str:
    digits = re.sub(r"\D", "", _latinize(str(value or "")))
    return digits


def _phone_tokens(value) -> list[str]:
    """Return the individual phone numbers inside a cell (people often give
    two numbers, e.g. "092863336 / 070568450")."""
    return [d for d in re.findall(r"\d{8,11}", _latinize(str(value or "")))]


def _clean_name(value) -> str:
    """Cell -> display name, or '' for NaN/empty cells."""
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    s = re.sub(r"\s+", " ", str(value)).strip(" -")
    return s if s.lower() != "nan" else ""


def _iso_date(value) -> str:
    """Convert a datetime/date cell or 'YYYY-MM-DD HH:MM:SS' text to date."""
    s = str(value or "").strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return ""


def _parse_session_dates(text: str) -> list[str]:
    """Best-effort parse of a Khmer session label → list of 'YYYY-MM-DD'.

    Handles both single- and multi-day labels, pairing each "ទី<day>" with
    the month/year that follows it (multi-day labels share a trailing month):

      "ថ្ងៃសុក្រ ទី១២ (រសៀល) និងថ្ងៃសៅរ៏ (ព្រឹក) ទី១៣ ខែមិថុនា ឆ្នាំ២០២៦"
      → ["2026-06-12", "2026-06-13"]

      "ថ្ងៃសុក្រ ទី៣១ ខែកក្កដា ឆ្នាំ២០២៦ និង (ព្រឹក) ថ្ងៃសៅរ៏ ទី១ ខែសីហា ឆ្នាំ២០២៦"
      → ["2026-07-31", "2026-08-01"]
    """
    t = _latinize(text or "")
    day_positions = [(m.start(), int(m.group(1))) for m in re.finditer(r"ថ្ងៃ\S*\s*ទី(\d{1,2})", t)]

    month_positions = []
    for name, num in KHMER_MONTHS.items():
        for m in re.finditer(name, t):
            month_positions.append((m.start(), num))
    month_positions.sort()

    year_positions = [(m.start(), int(m.group(1))) for m in re.finditer(r"ឆ្នាំ(\d{4})", t)]
    year_positions.sort()

    dates: list[str] = []
    for day_pos, day in day_positions:
        month = None
        for mpos, num in month_positions:
            if mpos > day_pos:
                month = num
                break
        if month is None and month_positions:
            month = month_positions[-1][1]
        year = None
        for ypos, y in year_positions:
            if ypos > day_pos:
                year = y
                break
        if year is None and year_positions:
            year = year_positions[-1][1]
        if month and year:
            dates.append(f"{year:04d}-{month:02d}-{day:02d}")
    return dates


def _parse_session_date(text: str) -> str:
    """First session date of a Khmer session label → 'YYYY-MM-DD', or ''."""
    dates = _parse_session_dates(text)
    return dates[0] if dates else ""


def _topic_summary(header: str) -> tuple[str, str, str]:
    """Extract (short_title, organizer, cpd_points) from a topic column header.

    Header looks like:
      ប្រធានបទ ជុំទី៣០ ៖ "...title..." (១០ពិន្ទុ ២០ដុល្លារ)
    """
    header = str(header)
    round_no = ""
    rm = re.search(r"ជុំទី(\d+)", header)
    if rm:
        round_no = rm.group(1)

    title = ""
    qm = re.search(r"[«‘\"“„](.*?)[»’\"”„]", header, re.S)
    if qm:
        title = qm.group(1).strip()
    if not title:
        title = header.strip()
    title = re.sub(r"\s+", " ", title).strip()
    title = title.strip(" «»‘\"“„’”'")

    points = ""
    pm = re.search(r"(\d{1,4})\s*ពិន្ទុ", _latinize(header))
    if pm:
        points = str(int(pm.group(1)))

    organizer = f"ជុំទី {round_no}" if round_no else ""
    return title, organizer, points


def _find_col(columns, *keywords) -> str | None:
    for kw in keywords:
        for col in columns:
            if kw in str(col):
                return col
    return None


# ------------------------------------------------------------ file detection
def _is_registration_file(path: Path) -> bool:
    df = pd.read_excel(path, nrows=1)
    cols = [str(c) for c in df.columns]
    return any("ឈ្មោះជាភាសាឡាតាំង" in c or "ឡាតាំង" in c or "English" in c for c in cols) or any(
        str(c).startswith("ប្រធានបទ") for c in cols
    )


def _is_certificate_file(path: Path) -> bool:
    df = pd.read_excel(path, nrows=1)
    cols = [str(c) for c in df.columns]
    return any("Confirm By Delivery Team" in c for c in cols) or any(
        kw in c for c in cols for kw in ["ឈ្មោះឱសថការី", "អង់គ្លេស", "English"]
    )


def df_kind(df: pd.DataFrame) -> str | None:
    """Classify a response tab: 'registration', 'certificate', or None."""
    cols = [str(c) for c in df.columns]
    if any("ឈ្មោះជាភាសាឡាតាំង" in c or "ឡាតាំង" in c or "English" in c for c in cols) or any(
        str(c).startswith("ប្រធានបទ") for c in cols
    ):
        return "registration"
    if any("Confirm By Delivery Team" in c for c in cols) or any(
        kw in c for c in cols for kw in ["ឈ្មោះឱសថការី", "អង់គ្លេស", "English"]
    ):
        return "certificate"
    return None


def _dedup_participants(participants: list[Participant]) -> list[Participant]:
    seen: dict[str, Participant] = {}
    for p in participants:
        key = normalize_name(p.name)
        if not key:
            continue
        if key not in seen:
            seen[key] = p
        else:
            existing = seen[key]
            existing.participant_id = existing.participant_id or p.participant_id
            existing.khmer_name = existing.khmer_name or p.khmer_name
            existing.phone = existing.phone or p.phone
            existing.department = existing.department or p.department
    return list(seen.values())


def _is_transformed_file(path: Path) -> bool:
    """Detect the combined 'Transformed ... with Certificates' workbook.

    One row per (participant, topic, session) selection. Columns include a
    full topic title, the selected session label, registration status, and a
    certificate pickup date column.
    """
    df = pd.read_excel(path, nrows=1)
    cols = [str(c) for c in df.columns]
    return any("វគ្គដែលបានជ្រើសរើស" in c for c in cols) and any(
        "ឈ្មោះប្រធានបទពេញ" in c for c in cols
    )


def load_transformed(path: Path) -> tuple[list[Participant], list[Training], list[Certificate]]:
    return transformed_from_df(pd.read_excel(path))


def transformed_from_df(
    df: pd.DataFrame,
) -> tuple[list[Participant], list[Training], list[Certificate]]:
    """Parse the combined 'Transformed' registration + certificate workbook.

    One row per (participant, topic, session). Only rows whose status is
    "បានចុះឈ្មោះ" (registered) and that carry a real session label produce a
    training. The certificate pickup date column is per row (the same date is
    repeated across a participant's rows), so a single pickup visit is mapped
    onto every one of that participant's trainings.
    """
    cols = list(df.columns)
    col_topic = _find_col(cols, "ឈ្មោះប្រធានបទពេញ")
    col_session = _find_col(cols, "វគ្គដែលបានជ្រើសរើស")
    col_status = _find_col(cols, "ស្ថានភាពចុះឈ្មោះ")
    col_name = _find_col(cols, "ឈ្មោះជាភាសាឡាតាំង", "ឡាតាំង", "English")
    col_khmer = _find_col(cols, "ឈ្មោះជាភាសាខ្មែរ", "ខ្មែរ", "Khmer")
    col_pcc = _find_col(cols, "លេខបញ្ជិកាឱសថការី", "បញ្ជិកា")
    col_department = _find_col(cols, "សមាជិកគណៈឱសថការី")
    col_phone = _find_col(cols, "លេខទូរស័ព្ទ")
    col_pickup = _find_col(cols, "បានទទួលវិញ្ញាបនបត្រ")

    participants: list[Participant] = []
    trainings: list[Training] = []
    certificates: list[Certificate] = []

    seen_trainings: set[tuple[str, str, str]] = set()
    for _, row in df.iterrows():
        status = _norm(row.get(col_status, "")) if col_status else ""
        if status != "បានចុះឈ្មោះ":
            continue

        session = _norm(row.get(col_session, "")) if col_session else ""
        if not session or session in ("មិនចុះឈ្មោះ",):
            continue

        name = _clean_name(row.get(col_name, "")) if col_name else ""
        if not name:
            continue

        participant_id = str(row.get(col_pcc, "")).strip() if col_pcc else ""
        p = Participant(
            participant_id=participant_id,
            name=name,
            khmer_name=_clean_name(row.get(col_khmer, "")) if col_khmer else "",
            profession="",
            department=str(row.get(col_department, "")).strip() if col_department else "",
            phone=_clean_name(row.get(col_phone, "")) if col_phone else "",
        )
        participants.append(p)

        title, organizer, points = _topic_summary(str(row.get(col_topic, "")) if col_topic else "")
        dates = _parse_session_dates(session)
        date = ", ".join(dates) if dates else ""

        dedupe_key = (participant_id, title, date)
        if dedupe_key in seen_trainings:
            continue
        seen_trainings.add(dedupe_key)

        trainings.append(
            Training(
                training_id="",
                participant_id=participant_id,
                participant_name=p.name,
                title=title,
                date=date,
                organizer=organizer,
                cpd_points=points,
                hours="",
                status="Registered",
            )
        )

        pickup = _iso_date(row.get(col_pickup, "")) if col_pickup else ""
        certificates.append(
            Certificate(
                certificate_id="",
                participant_id=participant_id,
                participant_name=p.name,
                khmer_name=p.khmer_name,
                training_title=date or title,
                certificate_number="",
                issued_date="",
                picked_up=bool(pickup),
                pickup_date=pickup,
                pickup_by="",
            )
        )

    return _dedup_participants(participants), trainings, certificates


def load_dfs(
    reg_dfs: list[pd.DataFrame], cert_dfs: list[pd.DataFrame]
) -> tuple[list[Participant], list[Training], list[Certificate]]:
    """Parse registration and certificate response tabs (e.g. from Google)."""
    participants: list[Participant] = []
    trainings: list[Training] = []
    for df in reg_dfs:
        ps, ts = registration_from_df(df)
        participants.extend(ps)
        trainings.extend(ts)

    participants = _dedup_participants(participants)

    certificates: list[Certificate] = []
    for df in cert_dfs:
        certificates.extend(certificates_from_df(df, participants))

    return participants, trainings, certificates


# ------------------------------------------------------------------ loading
def load_registration(path: Path) -> tuple[list[Participant], list[Training]]:
    return registration_from_df(pd.read_excel(path))


def registration_from_df(df: pd.DataFrame) -> tuple[list[Participant], list[Training]]:
    cols = list(df.columns)

    col_name = _find_col(cols, "ឈ្មោះជាភាសាឡាតាំង", "ឡាតាំង", "English", "ឈ្មោះជាអក្សរឡាតាំង")
    col_khmer = _find_col(cols, "ឈ្មោះជាភាសាខ្មែរ", "ខ្មែរ", "Khmer")
    col_pcc = _find_col(cols, "បញ្ជិកាឱសថការីកម្ពុជា", "លេខបញ្ជិកា")
    col_license = _find_col(cols, "សុពលភាពអាជ្ញាបណ្ឌឱសថការី")
    col_phone = _find_col(cols, "លេខទូរស័ព្ទ")
    col_gender = _find_col(cols, "ភេទ")
    col_province = _find_col(cols, "សមាជិកគណៈឱសថការី")
    col_level = _find_col(cols, "កម្រិតសិក្សា")
    col_ts = _find_col(cols, "v")
    if col_ts is None:
        for c in cols:
            if str(c).strip() == "v":
                col_ts = c
                break

    topic_cols = [c for c in cols if str(c).startswith("ប្រធានបទ")]

    participants: list[Participant] = []
    trainings: list[Training] = []

    for idx, row in df.iterrows():
        name = _clean_name(row.get(col_name, "")) if col_name else ""
        if not name:
            continue

        p = Participant(
            participant_id=str(row.get(col_pcc, "")).strip() if col_pcc else "",
            name=name,
            khmer_name=_clean_name(row.get(col_khmer, "")) if col_khmer else "",
            profession="",
            department=str(row.get(col_province, "")).strip() if col_province else "",
            phone=_clean_name(row.get(col_phone, "")) if col_phone else "",
        )
        participants.append(p)

        ts = _iso_date(row.get(col_ts, "")) if col_ts else ""
        for col in topic_cols:
            value = row.get(col, "")
            if value is None or pd.isna(value):
                continue
            value_str = str(value).strip()
            if not value_str or value_str == NOT_SELECTED:
                continue
            title, organizer, points = _topic_summary(col)
            for part in value_str.split(";"):
                part = part.strip()
                if not part:
                    continue
                date = _parse_session_date(part) or ts
                trainings.append(
                    Training(
                        training_id="",
                        participant_id=p.participant_id,
                        participant_name=p.name,
                        title=title,
                        date=date,
                        organizer=organizer,
                        cpd_points=points,
                        hours="",
                        status="Registered",
                    )
                )

    return participants, trainings


def load_certificates(path: Path, participants: list[Participant]) -> list[Certificate]:
    return certificates_from_df(pd.read_excel(path), participants)


def _parse_study_dates(study_text: str) -> list[str]:
    """Extract ISO dates from the free-text study-dates note.

    Handles formats like:
      "SOK SEILA – 14/02/26"
      "ឈ្មោះ «ក» – 14/02/26"
      "12/06/26"
      "2026-06-12"
    Returns a list of "YYYY-MM-DD" strings (best-effort).
    """
    text = _latinize(study_text or "")
    dates: list[str] = []

    # ISO format: 2026-06-12
    for m in re.finditer(r"(\d{4})-(\d{2})-(\d{2})", text):
        dates.append(f"{m.group(1)}-{m.group(2)}-{m.group(3)}")

    # DD/MM/YY or DD/MM/YYYY
    for m in re.finditer(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})", text):
        d, mo, y = m.group(1), m.group(2), m.group(3)
        if len(y) == 2:
            y = f"20{y}"
        try:
            dates.append(f"{int(y):04d}-{int(mo):02d}-{int(d):02d}")
        except ValueError:
            pass

    # Deduplicate preserving order
    seen: set[str] = set()
    result: list[str] = []
    for d in dates:
        if d not in seen:
            seen.add(d)
            result.append(d)
    return result


def certificates_from_df(
    df: pd.DataFrame, participants: list[Participant]
) -> list[Certificate]:
    cols = list(df.columns)

    # Certificate file actual columns (from Google Forms export):
    # [0] Timestamp  [1] mode (ផ្ទាល់ខ្លួន/ជំនួស)  [2] proxy name warning note
    # [3] Confirm By Delivery Team  [4] study dates note  [5] phone
    # [6] pickup date  [7] review note  [8] Khmer name  [9] English name
    col_name_en = _find_col(cols, "សរសេរឈ្មោះឱសថការី ជាភាសាអង់គ្លេស",
                            "ឈ្មោះឱសថការី ជាភាសាអង់គ្លេស", "ជាភាសាអង់គ្លេស",
                            "ឈ្មោះឱសថការី(ជាភាសាអង់គ្លេស)", "English")
    col_name_kh = _find_col(cols, "សរសេរឈ្មោះឱសថការី ជាភាសាខ្មែរ",
                            "ឈ្មោះឱសថការី ជាភាសាខ្មែរ", "ជាភាសាខ្មែរ",
                            "ឈ្មោះឱសថការី(ជាភាសាខ្មែរ)", "Khmer")
    col_ts = _find_col(cols, "Timestamp")
    col_mode = _find_col(cols, "ផ្ទាល់ខ្លួន", "មកទទួលវិញ្ញាបនបត្រ")
    # Proxy name is embedded in a long note column - parse it from the note field
    col_proxy_note = _find_col(cols, "ចំណុចសំខាន់", "ឈ្មោះអ្នកមកទទួលជំនួស")
    col_pickup = _find_col(cols, "ថ្ងៃ-ខែ-ឆ្នាំ ដែលបានមកទទួល", "បានមកទទួល", "ថ្ងៃ-ខែ-ឆ្នាំ")
    col_study = _find_col(cols, "សរសេរឈ្មោះឱសថការី និងបំពេញ", "ថ្ងៃ-ខែ-ឆ្នាំ សិក្សា", "សិក្សា")
    col_confirm = _find_col(cols, "Confirm By Delivery Team")
    col_phone = _find_col(cols, "លេខទូរស័ព្ទ")

    index: dict[str, str] = {}
    for p in participants:
        keys = [normalize_name(p.name), normalize_name(p.khmer_name)]
        keys += _phone_tokens(p.phone)
        for key in keys:
            if key:
                index.setdefault(key, p.participant_id)

    certificates: list[Certificate] = []
    for _, row in df.iterrows():
        name_en = _clean_name(row.get(col_name_en, "")) if col_name_en else ""
        name_kh = _clean_name(row.get(col_name_kh, "")) if col_name_kh else ""
        name = name_en or name_kh
        phone_tokens = _phone_tokens(row.get(col_phone, "")) if col_phone else []
        if not name and not phone_tokens:
            continue

        mode = _norm(row.get(col_mode, "")) if col_mode else ""
        # The proxy name is written in the note/warning column by the user
        picked_by = ""
        if col_proxy_note:
            proxy_note = _norm(row.get(col_proxy_note, ""))
            # If it contains N/A or is short/empty, it means they came in person
            if proxy_note and proxy_note.upper().strip() not in ("N/A", "NA", ""):
                picked_by = proxy_note
        if not picked_by and mode and "ជំនួស" in mode:
            picked_by = "អ្នកតំណាង"
        elif not picked_by:
            picked_by = "ខ្លួនផ្ទាល់"

        # "Confirm By Delivery Team" holds the name of the staff member who
        # handed the certificate out. A non-empty, non-negative value = picked up.
        # Empty / NaN / negative keywords = not yet handed over.
        confirm = _norm(row.get(col_confirm, "")) if col_confirm else ""
        confirm_lower = confirm.lower()
        _NOT_PICKED = {"", "no", "មិន", "nan", "n/a", "na", "none"}
        _NOT_PICKED_BIT = ("មិនទាន់", "verify", "verification", "again", "not yet")
        if confirm_lower in _NOT_PICKED or any(bit in confirm_lower for bit in _NOT_PICKED_BIT):
            picked_up = False
        else:
            # Any non-empty positive value (including a staff name) = confirmed
            picked_up = bool(confirm)

        pid = None
        for key in [normalize_name(name), normalize_name(name_kh)] + phone_tokens:
            if key and key in index:
                pid = index[key]
                break

        study_text = str(row.get(col_study, "")) if col_study else ""
        study_dates = _parse_study_dates(study_text)
        training_title = ", ".join(study_dates) if study_dates else _clean_name(study_text)

        pickup_date = _iso_date(row.get(col_pickup, ""))
        certificates.append(
            Certificate(
                certificate_id="",
                participant_id=pid or "",
                participant_name=name,
                khmer_name=name_kh,
                training_title=training_title,
                certificate_number="",
                issued_date="",
                picked_up=picked_up,
                pickup_date=pickup_date,
                pickup_by=picked_by,
            )
        )

    return certificates


def load_real_data(data_dir: Path) -> tuple[list[Participant], list[Training], list[Certificate]] | None:
    """Load the real Google-Forms exports, or return None if not detected."""
    reg_path = None
    cert_path = None
    transformed_path = None
    roots = [data_dir, data_dir / ".google"]
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.glob("*.xlsx")):
            if path.name.startswith("~$"):
                continue
            try:
                if transformed_path is None and _is_transformed_file(path):
                    transformed_path = path
                elif reg_path is None and _is_registration_file(path):
                    reg_path = path
                elif cert_path is None and _is_certificate_file(path):
                    cert_path = path
            except Exception:  # noqa: BLE001 - skip files that cannot be read
                continue

    if transformed_path is not None:
        return load_transformed(transformed_path)

    if reg_path is None and cert_path is None:
        return None

    participants: list[Participant] = []
    trainings: list[Training] = []
    if reg_path is not None:
        participants, trainings = load_registration(reg_path)

    participants = _dedup_participants(participants)

    certificates: list[Certificate] = []
    if cert_path is not None:
        certificates = load_certificates(cert_path, participants)

    return participants, trainings, certificates