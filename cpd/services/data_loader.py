"""Reads CPD records from Excel files in the data folder.

Expected files (per sheet/tab):
  participants.xlsx        - master list of participants
  trainings.xlsx           - training records of each participant
  certificate_pickup.xlsx  - CPD certificate pickup status

Data is cached in memory and automatically reloaded whenever a file's
modification time changes, so you can edit the Excel files while the
bot is running without restarting it.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from cpd.config import DATA_DIR

logger = logging.getLogger(__name__)

# Column name -> canonical internal key. Missing/renamed columns are tolerated
# by only mapping the columns that actually appear in each file.
PARTICIPANT_COLS = {
    "id": "participant_id",
    "participant_id": "participant_id",
    "code": "participant_id",
    "name": "name",
    "full_name": "name",
    "khmer_name": "khmer_name",
    "profession": "profession",
    "specialty": "profession",
    "department": "department",
    "email": "email",
    "phone": "phone",
}

TRAINING_COLS = {
    "id": "training_id",
    "training_id": "training_id",
    "participant_id": "participant_id",
    "participant_name": "participant_name",
    "name": "participant_name",
    "title": "title",
    "training_title": "title",
    "date": "date",
    "training_date": "date",
    "organizer": "organizer",
    "cpd_points": "cpd_points",
    "hours": "hours",
    "status": "status",
}

CERTIFICATE_COLS = {
    "id": "certificate_id",
    "certificate_id": "certificate_id",
    "participant_id": "participant_id",
    "participant_name": "participant_name",
    "name": "participant_name",
    "training_title": "training_title",
    "certificate_number": "certificate_number",
    "issued_date": "issued_date",
    "picked_up": "picked_up",
    "pickup_date": "pickup_date",
    "pickup_by": "pickup_by",
}

FILE_COLUMNS = {
    "participants.xlsx": PARTICIPANT_COLS,
    "trainings.xlsx": TRAINING_COLS,
    "certificate_pickup.xlsx": CERTIFICATE_COLS,
}


@dataclass
class Course:
    course_id: str = ""
    title: str = ""
    date: str = ""
    cpd_points: str = ""
    link: str = ""
    status: str = ""
    fee: float = 0.0


@dataclass
class Participant:
    participant_id: str
    name: str
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


def _norm(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (ValueError, TypeError):
        pass
    return str(value).strip()


def _clean_int(value: Any) -> str:
    s = _norm(value)
    if s.isdigit():
        return str(int(s))
    return s


def _as_bool(value: Any) -> bool:
    """Convert common 'picked up' representations to a boolean."""
    s = _norm(value).lower()
    if s in {"1", "true", "yes", "y", "ចាស", "បាន", "picked", "picked up", "done"}:
        return True
    if s in {"0", "false", "no", "n", "no/មិនទាន់", "not", "not yet", "not picked up", "no "}:
        return False
    return bool(value) if not s else False


def _parse_fee(value: Any) -> float:
    """Parse a course fee (USD) from a cell, tolerating empty/text/currency."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace("$", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _read_sheet(path: Path, column_map: dict[str, str]) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=0)
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

    rename = {}
    for col in df.columns:
        if col in column_map:
            rename[col] = column_map[col]
    df = df.rename(columns=rename)

    for col in df.columns:
        if "date" in col and "datetime" in str(df[col].dtype):
            df[col] = df[col].dt.strftime("%Y-%m-%d")
        elif "date" in col:
            df[col] = df[col].astype(str)
    return df


class CpdData:
    """Loads and caches the three Excel data files."""

    def __init__(self, data_dir: Path | None = None):
        self._data_dir = Path(data_dir or DATA_DIR)
        self._lock = threading.RLock()
        self._mtime: dict[str, int] = {}
        self._last_google_refresh = 0.0
        self._google_reg_dfs: list[Any] = []
        self._google_cert_dfs: list[Any] = []
        self._google_digest = ""
        self.participants: list[Participant] = []
        self.trainings: list[Training] = []
        self.certificates: list[Certificate] = []
        self.courses: list[Course] = []
        self._trainings_by_id: dict[str, list[Training]] = {}
        self._trainings_by_name: dict[str, list[Training]] = {}
        self._certs_by_id: dict[str, list[Certificate]] = {}
        self._certs_by_name: dict[str, list[Certificate]] = {}
        self._loaded = False

    # ------------------------------------------------------------------ API
    def _file_mtimes(self) -> dict[str, int]:
        """Map relative filename -> last-modified time for every data file."""
        mtimes: dict[str, int] = {}
        roots = [self._data_dir, self._data_dir / ".google"]
        for root in roots:
            if not root.exists():
                continue
            for path in sorted(root.glob("*.xlsx")):
                mtimes[str(path)] = int(path.stat().st_mtime)
        from cpd.services.registrations import REGISTRATIONS_FILE
        if REGISTRATIONS_FILE.exists():
            mtimes[str(REGISTRATIONS_FILE)] = int(REGISTRATIONS_FILE.stat().st_mtime)
        return mtimes

    def _maybe_refresh_google(self) -> bool:
        """Query Google Sheets at an interval; return True if data changed."""
        import hashlib
        import time

        from cpd.services import google_sheets
        from cpd.config import (
            GS_ID_R,
            GS_ID_C,
            GOOGLE_SHEET_REFRESH_MINUTES,
            GOOGLE_SHEET_SHEET_NAMES,
        )
        from cpd.services.real_data import df_kind

        if not GS_ID_R:
            return False
        now = time.time()
        interval = GOOGLE_SHEET_REFRESH_MINUTES * 60
        if self._last_google_refresh and now - self._last_google_refresh < interval:
            return False
        self._last_google_refresh = now

        reg, cert = [], []
        for sid in (GS_ID_R, GS_ID_C):
            if not sid:
                continue
            for df in google_sheets.fetch_tabs(
                sid, sheet_names=GOOGLE_SHEET_SHEET_NAMES
            ).values():
                kind = df_kind(df) if not df.empty else None
                if kind == "registration":
                    reg.append(df)
                elif kind == "certificate":
                    cert.append(df)
        if not reg and not cert:
            logger.warning(
                "No CPD response tabs found in Google Sheets %s. Make each "
                "sheet shared with 'Anyone with the link -> Viewer'.",
                GS_ID_R,
            )
            return False

        digest = hashlib.sha1(f"{len(reg)},{len(cert)}:{reg}{cert}".encode()).hexdigest()
        if digest != self._google_digest:
            self._google_digest = digest
            self._google_reg_dfs, self._google_cert_dfs = reg, cert
            logger.info("Google Sheets data updated (%d reg, %d cert tabs)",
                        len(reg), len(cert))
            return True
        return False

    def ensure_loaded(self) -> None:
        """Reload if any file changed on disk. Safe to call on every request."""
        with self._lock:
            changed = not self._loaded
            if self._maybe_refresh_google():
                changed = True
            mtimes = self._file_mtimes()
            if set(mtimes) != set(self._mtime):
                changed = True
            for fname, mtime in mtimes.items():
                if self._mtime.get(fname) != mtime:
                    self._mtime[fname] = mtime
                    changed = True
            if changed:
                self._load()

    def reload(self) -> None:
        with self._lock:
            self._mtime = self._file_mtimes()
            self._load()

    # -------------------------------------------------------------- internal
    def _load(self) -> None:
        with self._lock:
            self.participants = []
            self.trainings = []
            self.certificates = []
            self.courses = []

            # Load courses first
            course_path = self._data_dir / "courses.xlsx"
            if course_path.exists():
                df = pd.read_excel(course_path)
                # Normalise column names (strip whitespace, lowercase) so the
                # lookup works regardless of how the header is capitalised in
                # the spreadsheet.
                df.columns = [str(c).strip().lower().replace(" ", "_")
                              for c in df.columns]
                for _, row in df.iterrows():
                    self.courses.append(
                        Course(
                            course_id=_norm(row.get("course_id", "")),
                            title=_norm(row.get("title", "")),
                            date=_norm(row.get("date", "")),
                            cpd_points=_norm(row.get("cpd_points", "")),
                            link=_norm(row.get("link", "")),
                            status=_norm(row.get("status", "")),
                            fee=_parse_fee(row.get("fee", 0)),
                        )
                    )

            # Prefer live Google Sheets tabs when they are configured.
            if self._google_reg_dfs or self._google_cert_dfs:
                from cpd.services.real_data import load_dfs

                self.participants, self.trainings, self.certificates = load_dfs(
                    self._google_reg_dfs, self._google_cert_dfs
                )
                self._rebuild_indices()
                self._loaded = True
                return

            # Otherwise use the real Google-Forms xlsx exports when present.
            from cpd.services.real_data import load_real_data

            real = load_real_data(self._data_dir)
            if real is not None:
                self.participants, self.trainings, self.certificates = real
                self._merge_registrations()
                self._rebuild_indices()
                self._loaded = True
                return

            p_path = self._data_dir / "participants.xlsx"
            if p_path.exists():
                df = _read_sheet(p_path, FILE_COLUMNS["participants.xlsx"])
                for _, row in df.iterrows():
                    self.participants.append(
                        Participant(
                            participant_id=_clean_int(row.get("participant_id", "")),
                            name=_norm(row.get("name", "")),
                            khmer_name=_norm(row.get("khmer_name", "")),
                            profession=_norm(row.get("profession", "")),
                            department=_norm(row.get("department", "")),
                            email=_norm(row.get("email", "")),
                            phone=_norm(row.get("phone", "")),
                        )
                    )

            t_path = self._data_dir / "trainings.xlsx"
            if t_path.exists():
                df = _read_sheet(t_path, FILE_COLUMNS["trainings.xlsx"])
                for _, row in df.iterrows():
                    self.trainings.append(
                        Training(
                            training_id=_clean_int(row.get("training_id", "")),
                            participant_id=_clean_int(row.get("participant_id", "")),
                            participant_name=_norm(row.get("participant_name", "")),
                            title=_norm(row.get("title", "")),
                            date=_norm(row.get("date", "")),
                            organizer=_norm(row.get("organizer", "")),
                            cpd_points=_norm(row.get("cpd_points", "")),
                            hours=_norm(row.get("hours", "")),
                            status=_norm(row.get("status", "")),
                        )
                    )

            c_path = self._data_dir / "certificate_pickup.xlsx"
            if c_path.exists():
                df = _read_sheet(c_path, FILE_COLUMNS["certificate_pickup.xlsx"])
                for _, row in df.iterrows():
                    self.certificates.append(
                        Certificate(
                            certificate_id=_clean_int(row.get("certificate_id", "")),
                            participant_id=_clean_int(row.get("participant_id", "")),
                            participant_name=_norm(row.get("participant_name", "")),
                            training_title=_norm(row.get("training_title", "")),
                            certificate_number=_norm(row.get("certificate_number", "")),
                            issued_date=_norm(row.get("issued_date", "")),
                            picked_up=_as_bool(row.get("picked_up", "")),
                            pickup_date=_norm(row.get("pickup_date", "")),
                            pickup_by=_norm(row.get("pickup_by", "")),
                        )
                    )

            self._rebuild_indices()
            self._loaded = True

    def _merge_registrations(self) -> None:
        """Merge in-bot course registrations into participants + trainings."""
        from cpd.services.registrations import load_registrations

        by_name: dict[str, Participant] = {}
        for p in self.participants:
            key = (p.name or "").strip().lower()
            if key:
                by_name.setdefault(key, p)

        for reg in load_registrations():
            name = (reg.get("name") or "").strip()
            if not name:
                continue
            participant_id = (reg.get("participant_id") or "").strip()
            phone = (reg.get("phone") or "").strip()
            location = (reg.get("location") or "").strip()

            p = by_name.get(name.lower())
            if p is None:
                p = Participant(
                    participant_id=participant_id,
                    name=name,
                    phone=phone,
                    department=location,
                )
                self.participants.append(p)
                by_name[name.lower()] = p
            elif participant_id and not p.participant_id:
                p.participant_id = participant_id
            elif phone and not p.phone:
                p.phone = phone

            course_title = (reg.get("course_title") or "").strip()
            course_date = (reg.get("course_date") or "").strip()
            points = (reg.get("cpd_points") or "").strip()
            self.trainings.append(
                Training(
                    participant_id=p.participant_id,
                    participant_name=p.name,
                    title=course_title or (reg.get("course_id") or "").strip(),
                    date=course_date,
                    cpd_points=points,
                    status="Registered",
                )
            )

    def _rebuild_indices(self) -> None:
        self._trainings_by_id = {}
        self._trainings_by_name = {}
        for t in self.trainings:
            if t.participant_id:
                self._trainings_by_id.setdefault(t.participant_id, []).append(t)
            if t.participant_name:
                self._trainings_by_name.setdefault(t.participant_name.lower(), []).append(t)
        
        self._certs_by_id = {}
        self._certs_by_name = {}
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
        """Find one participant by id or by exact name."""
        for p in self.participants:
            if p.participant_id and p.participant_id == identifier:
                return p
            if p.name and p.name.lower() == identifier.lower():
                return p
            if p.khmer_name and p.khmer_name == identifier:
                return p
        return None

    def trainings_for(self, participant_id: str = "", participant_name: str = "", khmer_name: str = "") -> list[Training]:
        out = []
        seen = set()
        if participant_id:
            for t in self._trainings_by_id.get(participant_id, []):
                out.append(t)
                seen.add(id(t))
        
        names_to_check = [n for n in (participant_name, khmer_name) if n]
        for name in names_to_check:
            # 1. Exact match (case-insensitive)
            for t in self._trainings_by_name.get(name.lower(), []):
                if id(t) not in seen:
                    out.append(t)
                    seen.add(id(t))
            
            # 2. Normalized match fallback
            from cpd.services.search import normalize_name
            norm_name = normalize_name(name)
            if not norm_name:
                continue
                
            for t in self.trainings:
                if id(t) not in seen:
                    t_name = normalize_name(t.participant_name or "")
                    if norm_name and (
                        norm_name == t_name or
                        norm_name in t_name or t_name in norm_name
                    ):
                        out.append(t)
                        seen.add(id(t))

        return out

    def certificates_for(self, participant_id: str = "", participant_name: str = "", khmer_name: str = "") -> list[Certificate]:
        out = []
        seen = set()
        if participant_id:
            for c in self._certs_by_id.get(participant_id, []):
                out.append(c)
                seen.add(id(c))
                
        names_to_check = [n for n in (participant_name, khmer_name) if n]
        for name in names_to_check:
            # 1. Exact match (case-insensitive)
            for c in self._certs_by_name.get(name.lower(), []):
                if id(c) not in seen:
                    out.append(c)
                    seen.add(id(c))
                    
            # 2. Normalized match fallback
            from cpd.services.search import normalize_name
            norm_name = normalize_name(name)
            if not norm_name:
                continue
                
            for c in self.certificates:
                if id(c) not in seen:
                    c_name = normalize_name(c.participant_name or "")
                    c_khmer = normalize_name(c.khmer_name or "")
                    if norm_name and (
                        norm_name == c_name or norm_name == c_khmer or
                        norm_name in c_name or norm_name in c_khmer
                    ):
                        out.append(c)
                        seen.add(id(c))

        return out