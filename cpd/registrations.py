"""Storage for course registrations made through the bot.

New registrations are appended to a local CSV file for now. When the loader
merges them, each registration becomes a participant (if new) plus a Training
record, so the bot shows them immediately. The file is meant to be copied
into the master data later.
"""

from __future__ import annotations

import csv
import json
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
    "qr_md5",
    "payment_status",
    "paid_at",
    "status",
]


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
        writer.writerow(row)


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
            if r.get("payment_status") == "Pending" or \
                    r.get("status") == "Pending payment":
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


def mark_paid(bill_number: str, payment_status: str = "Paid") -> bool:
    """Update the payment fields of the registration with *bill_number*.

    Registrations are stored while unpaid too (so the admin can see pending
    fees). This flips the row to paid once Bakong confirms the transaction.
    """
    if not bill_number:
        return False
    rows = load_registrations()
    updated = False
    paid_at = time.strftime("%Y-%m-%d %H:%M:%S")
    for row in rows:
        if str(row.get("bill_number", "")).strip() == str(bill_number).strip():
            row["payment_status"] = payment_status
            row["paid_at"] = paid_at
            if payment_status == "Paid":
                row["status"] = "Registered"
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