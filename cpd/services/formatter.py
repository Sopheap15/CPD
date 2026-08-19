"""Builds human-readable reports from participant data.

All output is bilingual (English then Khmer) and rendered with Telegram
HTML formatting. Telegram only supports a fixed set of HTML tags (`b`,
`code`, `a`, ...) - `<br/>` and `<pre>`-style monospace tables do not wrap
on mobile screens, so records are rendered as compact bullet lines that wrap
naturally. Line breaks use plain newlines (`\\n`).
"""

from __future__ import annotations

import html
from typing import Iterable

from cpd.services.data_loader import Certificate, Participant, Training
from cpd.i18n import inline, t

NL = "\n"
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


# ------------------------------------------------------------------ header
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


# ------------------------------------------------------------------ records
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


def _certificate_line(c: Certificate, matched_training: Training | None = None) -> str:
    status = inline("picked_up") if c.picked_up else inline("not_picked_up")
    bits = [f"<b>{_esc(status)}</b>"]
    # Show the matched training title if available, otherwise the raw study date
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
    else:
        status = inline("not_picked_up")
        line = "• " + " · ".join(bits)
        return line


def training_lines(trainings: Iterable[Training]) -> str:
    sorted_trainings = sorted(trainings, key=lambda tr: tr.date or "", reverse=True)
    lines = [_training_line(tr) for tr in sorted_trainings]
    return NL.join(line for line in lines if line)


def _match_training_for_cert(
    c: Certificate, trainings: list[Training]
) -> Training | None:
    """Find the training whose date matches c.training_title (a study date)."""
    study_date = c.training_title.strip() if c.training_title else ""
    if not study_date:
        return None
    for tr in trainings:
        if tr.date and tr.date.startswith(study_date):
            return tr
        if study_date and tr.date and tr.date == study_date:
            return tr
    return None


def certificate_lines(
    certificates: Iterable[Certificate],
    trainings: Iterable[Training] | None = None,
) -> str:
    certs = sorted(certificates, key=lambda c: c.training_title or "", reverse=True)
    tr_list = list(trainings) if trainings else []
    lines = []
    for c in certs:
        matched = _match_training_for_cert(c, tr_list)
        lines.append(_certificate_line(c, matched))
    return NL.join(lines)


def _cert_status_for_trainings(
    trainings: list[Training], certificates: list[Certificate]
) -> list[str]:
    """Show certificate pickup status only for trainings that have a pickup record.

    If nobody has come to pick up at all, return an empty list so the caller
    can show t("no_certificate") instead.
    """
    if not certificates:
        return []  # Nobody came to the office yet

    lines = []
    for c in sorted(certificates, key=lambda c: c.training_title or "", reverse=True):
        # Find the matching training by comparing study date to training date
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
        line = f"• <b>{_esc(status)}</b>"
        if title_str:
            line += f" · {title_str}"
        if c.picked_up and c.pickup_date:
            extra = f"បានទទួលថ្ងៃទី {_esc(_date(c.pickup_date))}"
            pb = c.pickup_by.strip() if c.pickup_by else ""
            if pb and pb.lower() not in ("nan", "-", "n/a"):
                extra += f" ដោយ {_esc(pb)}"
            line = f"• {extra}"
        else:
            status = inline("not_picked_up")
            line = f"• <b>{_esc(status)}</b>"
            if title_str:
                line += f" · {title_str}"
        lines.append(line)
    return lines


def section_heading(heading_key: str) -> str:
    return f"<b>{_esc(inline(heading_key))}</b>"


# ------------------------------------------------------------------ reports
def _counts(trainings: Iterable[Training], certificates: Iterable[Certificate]) -> list[str]:
    trainings = list(trainings)
    certificates = list(certificates)

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
        # Expected = one cert per training session
        # picked   = certificates confirmed received
        # (cert records only exist when someone came to the office)
        total_expected = len(trainings)
        lines.append(_row("វិញ្ញាបនបត្រដែលបានទទួល", f"{picked} / {total_expected}"))
        lines.append(_row("វិញ្ញាបនបត្រមិនទាន់ទទួល", str(total_expected - picked)))
    return lines


def summary_sections(
    p: Participant,
    trainings: Iterable[Training],
    certificates: Iterable[Certificate],
) -> list[str]:
    """Return the full report as a list of standalone messages."""
    head = [participant_header(p), ""] + _counts(trainings, certificates)

    sections: list[str] = [NL.join(head)]

    trainings = list(trainings)
    certificates = list(certificates)

    if trainings:
        sections.append(NL + section_heading("section_training") + NL + training_lines(trainings))
    else:
        sections.append(NL + section_heading("section_training") + NL + t("no_training"))

    cert_lines = _cert_status_for_trainings(trainings, certificates)
    if cert_lines:
        cert_text = NL.join(cert_lines)
    else:
        cert_text = t("no_certificate")
    sections.append(NL + section_heading("section_certificate") + NL + cert_text + NL + NL + t("further_info"))

    return sections


def summary_report(p: Participant, trainings: Iterable[Training], certificates: Iterable[Certificate]) -> str:
    """Combined report (all sections joined)."""
    return NL.join(summary_sections(p, trainings, certificates))


def training_report(participant_name: str, trainings: Iterable[Training]) -> str:
    if not trainings:
        return f"<b>{_esc(participant_name)}</b>{NL}{t('no_training')}{NL}{NL}{t('further_info')}"
    return (
        f"<b>{_esc(participant_name)}</b> — {_esc(inline('section_training'))}"
        f"{NL}{training_lines(trainings)}{NL}{NL}{t('further_info')}"
    )


def certificate_report(participant_name: str, certificates: Iterable[Certificate]) -> str:
    if not certificates:
        return f"<b>{_esc(participant_name)}</b>{NL}{t('no_certificate')}{NL}{NL}{t('further_info')}"
    return (
        f"<b>{_esc(participant_name)}</b> — {_esc(inline('section_certificate'))}"
        f"{NL}{certificate_lines(certificates)}{NL}{NL}{t('further_info')}"
    )