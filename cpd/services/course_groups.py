"""Maps each course (by its Course ID) to the Telegram group chat for it.

Bots cannot create Telegram groups, so an admin creates one group per course,
adds this bot as an administrator, then runs ``/admin_group <Course ID>``
inside that group. The bot remembers the mapping and, after a participant
registers, sends them an invite link to join.

The mapping is stored in ``data/course_groups.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

from cpd.config import DATA_DIR

COURSE_GROUPS_FILE = Path(DATA_DIR) / "course_groups.json"


def _load() -> dict[str, int]:
    if not COURSE_GROUPS_FILE.exists():
        return {}
    try:
        with open(COURSE_GROUPS_FILE, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        return {str(k): int(v) for k, v in (raw or {}).items() if str(v).lstrip("-").isdigit()}
    except Exception:
        return {}


def get_group_chat_id(course_id: str) -> int | None:
    """Return the group chat id registered for a course, or None."""
    return _load().get(str(course_id).strip())


def set_group_chat_id(course_id: str, chat_id: int) -> None:
    """Register a Telegram group as the chat for a course."""
    data = _load()
    data[str(course_id).strip()] = int(chat_id)
    COURSE_GROUPS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(COURSE_GROUPS_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def clear_group_chat_id(course_id: str) -> None:
    """Remove the group mapping for a course, if any."""
    data = _load()
    if str(course_id).strip() in data:
        del data[str(course_id).strip()]
        COURSE_GROUPS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(COURSE_GROUPS_FILE, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)


def all_group_mappings() -> dict[str, int]:
    """Return all course_id -> chat_id mappings."""
    return _load()


def course_groups_file_mtime() -> int | None:
    """Return the last-modified time of the mapping file, or None."""
    if not COURSE_GROUPS_FILE.exists():
        return None
    return int(COURSE_GROUPS_FILE.stat().st_mtime)