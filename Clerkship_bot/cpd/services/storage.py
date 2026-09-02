"""Storage for linking Telegram User IDs to participant names."""

import json
from pathlib import Path
from typing import Optional

from cpd.config import DATA_DIR

LINKS_FILE = Path(DATA_DIR) / "telegram_links.json"

def get_linked_name(telegram_id: int) -> Optional[str]:
    """Return the participant name linked to this Telegram ID, or None."""
    if not LINKS_FILE.exists():
        return None
    try:
        with open(LINKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get(str(telegram_id))
    except Exception:
        return None

def link_account(telegram_id: int, name: str) -> None:
    """Link a Telegram ID to a participant name."""
    data = {}
    if LINKS_FILE.exists():
        try:
            with open(LINKS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
    data[str(telegram_id)] = name
    LINKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LINKS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def unlink_account(telegram_id: int) -> None:
    """Remove the link for a Telegram ID."""
    if not LINKS_FILE.exists():
        return
    try:
        with open(LINKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if str(telegram_id) in data:
            del data[str(telegram_id)]
            with open(LINKS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def list_all_links() -> dict[str, str]:
    """Return all telegram_id -> participant_name mappings."""
    if not LINKS_FILE.exists():
        return {}
    try:
        with open(LINKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def find_telegram_id_by_name(name: str) -> Optional[str]:
    """Find the Telegram ID linked to a given participant name (case-insensitive)."""
    links = list_all_links()
    name_lower = name.strip().lower()
    for tid, pname in links.items():
        if pname.strip().lower() == name_lower:
            return tid
    return None


def admin_unlink_by_name(name: str) -> bool:
    """Unlink the Telegram ID associated with a participant name. Returns True if found."""
    tid = find_telegram_id_by_name(name)
    if tid is None:
        return False
    unlink_account(int(tid))
    return True
