"""Storage for course registrations made through the bot.

New registrations are appended to a local CSV file for now. When the loader
merges them, each registration becomes a participant (if new) plus a Training
record, so the bot shows them immediately. The file is meant to be copied
into the master data later.
"""

from __future__ import annotations

import csv
import secrets
import time
from pathlib import Path

from cpd.config import DATA_DIR

REGISTRATIONS_FILE = Path(DATA_DIR) / "in_bot_registrations.csv"

REGISTRATION_COLUMNS = [
    "registered_at",
    "telegram_id",
    "name",
    "participant_id",
    "phone",
    "location",
    "course_id",
    "course_title",
    "course_date",
    "cpd_points",
    "fee",
    "currency",
    "bill_number",
    "payment_ref",
    "status",
    "pickup_at",
    "pickup_by",
]


def generate_payment_ref() -> str:
    """Return a random 10-digit receipt number for easy searching."""
    return f"{secrets.randbelow(10**10):010d}"


def _empty_row() -> dict:
    return {col: "" for col in REGISTRATION_COLUMNS}


def _ensure_columns() -> None:
    """Migrate the CSV header to REGISTRATION_COLUMNS if it has changed.

    Older files were written without the payment columns; rewriting them with
    the current header keeps rows aligned.
    """
    if not REGISTRATIONS_FILE.exists():
        return
    try:
        with open(REGISTRATIONS_FILE, "r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            header = reader.fieldnames or []
        if header == REGISTRATION_COLUMNS:
            return
    except Exception:
        return
    rows = load_registrations()
    REGISTRATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRATIONS_FILE, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=REGISTRATION_COLUMNS)
        writer.writeheader()
        for r in rows:
            writer.writerow({col: r.get(col, "") for col in REGISTRATION_COLUMNS})


def append_registration(record: dict) -> None:
    """Append one registration row to the CSV file."""
    _ensure_columns()
    row = _empty_row()
    row.update({k: v for k, v in record.items() if k in REGISTRATION_COLUMNS})
    if not row.get("registered_at"):
        row["registered_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    REGISTRATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    new_file = not REGISTRATIONS_FILE.exists()
    with open(REGISTRATIONS_FILE, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=REGISTRATION_COLUMNS)
        if new_file:
            writer.writeheader()
        elif not _file_ends_with_newline():
            # csv module writes with its own line terminator; a file that was
            # hand-edited (or left without a trailing newline) would otherwise
            # merge this row onto the previous line.
            fh.write("\r\n")
        writer.writerow(row)


def _file_ends_with_newline() -> bool:
    """True when the CSV file's last byte is a line terminator."""
    try:
        with open(REGISTRATIONS_FILE, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            if size < 1:
                return True
            fh.seek(-1, 2)
            return fh.read(1) in (b"\n", b"\r")
    except Exception:
        return True


def append_pickup(name: str, pickup_by: str = "",
                  course_id: str = "", course_title: str = "",
                  course_date: str = "") -> None:
    """Record a certificate pickup visit against a pharmacist name + course.

    The pickup is stored in the same CSV as registrations (which already holds
    the pharmacist's name). A trainee may wait until several certificates are
    ready and collect them in one visit, so the course being collected is
    recorded to make it clear which certificate was picked up.
    """
    append_registration({
        "name": (name or "").strip(),
        "course_id": (course_id or "").strip(),
        "course_title": (course_title or "").strip(),
        "course_date": (course_date or "").strip(),
        "status": "Picked up",
        "pickup_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "pickup_by": (pickup_by or "").strip(),
    })


def load_registrations() -> list[dict]:
    """Read all in-bot registrations as a list of dicts."""
    if not REGISTRATIONS_FILE.exists():
        return []
    try:
        with open(REGISTRATIONS_FILE, "r", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except Exception:
        return []


def registrations_file_mtime() -> int | None:
    """Return the last-modified time of the CSV, or None if it doesn't exist."""
    if not REGISTRATIONS_FILE.exists():
        return None
    return int(REGISTRATIONS_FILE.stat().st_mtime)


def find_registration(telegram_id: int, course_id: str) -> dict | None:
    """Return an existing registration for a Telegram ID + course, if any.

    Rows left in "Pending payment" state (QR sent, not yet paid, or the
    payment window expired) are not treated as real registrations, so the
    participant can register again.
    """
    for r in load_registrations():
        if str(r.get("telegram_id", "")).strip() == str(telegram_id).strip() and \
                str(r.get("course_id", "")).strip() == str(course_id).strip():
            if r.get("status") == "Pending payment":
                continue
            return r
    return None


def has_duplicate(telegram_id: int, course_id: str) -> bool:
    """True if this Telegram account already registered for the course."""
    return find_registration(telegram_id, course_id) is not None


def latest_registration_for_user(telegram_id: int) -> dict | None:
    """Return the most recent registration made by this Telegram account.

    Used to skip asking returning participants for their details again.
    """
    rows = [r for r in load_registrations()
            if str(r.get("telegram_id", "")).strip() == str(telegram_id).strip()
            and r.get("name")]
    if not rows:
        return None
    rows.sort(key=lambda r: r.get("registered_at", ""))
    return rows[-1]


def registration_by_name(telegram_id: int, name: str) -> dict | None:
    """Return the latest registration whose name matches *name* (case-insensitive).

    Lets a returning participant be recognized by their full name without
    having to re-enter phone/license/location.
    """
    key = (name or "").strip().lower()
    if not key:
        return None
    rows = [
        r for r in load_registrations()
        if str(r.get("telegram_id", "")).strip() == str(telegram_id).strip()
        and (r.get("name") or "").strip().lower() == key
        and r.get("name")
    ]
    if not rows:
        return None
    rows.sort(key=lambda r: r.get("registered_at", ""))
    return rows[-1]


def has_payment_ref(ref: str) -> bool:
    """Check if a payment reference has already been used in any registration."""
    if not ref:
        return False
    rows = load_registrations()
    for r in rows:
        if r.get("payment_ref") == ref:
            return True
    return False

def mark_paid(bill_number: str, status: str = "Paid") -> bool:
    """Update the payment fields of the registration with *bill_number*.

    Registrations are stored while unpaid (so the admin can see pending
    fees). This flips the row to paid once receipt verification succeeds.
    """
    if not bill_number:
        return False
    rows = load_registrations()
    updated = False
    for row in rows:
        if str(row.get("bill_number", "")).strip() == str(bill_number).strip():
            row["status"] = status
            updated = True
    if not updated:
        return False
    _write(rows)
    return True


def delete_registration(telegram_id: int | str, course_id: str) -> bool:
    """Remove the registration for a Telegram ID + course.

    Returns True when at least one row was removed.
    """
    rows = load_registrations()
    kept = [
        r for r in rows
        if not (str(r.get("telegram_id", "")).strip() == str(telegram_id).strip()
                and str(r.get("course_id", "")).strip() == str(course_id).strip())
    ]
    if len(kept) == len(rows):
        return False
    _write(kept)
    return True


def clear_registrations() -> int:
    """Delete every in-bot registration row. Returns how many were removed."""
    count = len(load_registrations())
    _write([])
    return count


def _write(rows: list[dict]) -> None:
    REGISTRATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRATIONS_FILE, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=REGISTRATION_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)