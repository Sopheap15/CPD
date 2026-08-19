"""Flexible name search used to resolve a user's typed name to a participant."""

from __future__ import annotations

import unicodedata
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any, Iterable

from cpd.services.data_loader import Participant

if TYPE_CHECKING:
    from cpd.services.data_loader import CpdData

# Only offer alternatives when the best match is clearly better than the second.
AUTO_SELECT_MARGIN = 0.25


def normalize_name(name: str) -> str:
    """Lowercase, strip diacritics and collapse whitespace for comparison."""
    name = name.replace("\u200b", "").replace("\u200c", "")
    text = unicodedata.normalize("NFKD", name).strip().lower()
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.split())


def _score(candidate: str, query: str) -> tuple[float, int]:
    """Return (similarity, length bonus) used to rank matches.

    Higher is better. Exact matches win, followed by substring matches;
    otherwise we fall back to a fuzzy ``difflib`` ratio.
    """
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


def rank_candidates(query: str, candidates: Iterable[str], limit: int = 6) -> list[str]:
    """Return candidate names ranked by similarity to *query*."""
    q = normalize_name(query)
    if not q:
        return []

    scored = []
    for cand in candidates:
        base, bonus = _score(cand, q)
        if base >= 0.55:  # fuzzy threshold
            scored.append((base + 0.0001 * bonus, cand))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [name for _, name in scored[:limit]]


def exact_participant(participants: list[Participant], name: str) -> Participant | None:
    """Find a participant whose Latin or Khmer name matches *name* exactly."""
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
    """Resolve a typed name to a single participant or a shortlist.

    Returns ``(subset, shortlist, auto_selected)`` where:
      * ``subset``  -> the chosen participant (or a name-only placeholder when
                       the person only exists in trainings/certificates, or
                       None if undecided)
      * ``shortlist`` -> ranked list of candidate names to present
      * ``auto_selected`` -> True when the best match was confident enough
    """
    ranked = rank_candidates(query, names)
    if not ranked:
        return None, [], False

    best_name = ranked[0]

    if len(ranked) == 1:
        return (
            exact_participant(participants, best_name)
            or Participant(participant_id="", name=best_name),
            ranked,
            True,
        )

    # Auto-select when the top match is much better than the runner-up.
    best_score, _ = _score(best_name, query)
    runner_score, _ = _score(ranked[1], query) if len(ranked) > 1 else (0.0, 0)

    if best_score - runner_score >= AUTO_SELECT_MARGIN:
        return (
            exact_participant(participants, best_name)
            or Participant(participant_id="", name=best_name),
            ranked,
            True,
        )

    return None, ranked, False


def find_best(participants: list[Participant], name: str) -> Participant | None:
    """Return the participant whose Latin or Khmer name matches *name* exactly.

    Never guesses: a name that is not in the master list returns None so the
    caller can fall back to a trainings/certificates-only record instead of
    showing a different person's data.
    """
    return exact_participant(participants, name)


def find_participant_by_secret(participants: list[Participant], secret: str) -> Participant | None:
    """Find a participant by their participant ID or Phone Number."""
    s = secret.strip().lower()
    if not s:
        return None
    
    # Try exact participant_id match
    for p in participants:
        if p.participant_id and p.participant_id.strip().lower() == s:
            return p
            
    # Try phone number match
    from cpd.services.real_data import _norm_phone, _phone_tokens
    s_phone = _norm_phone(s)
    if s_phone:
        for p in participants:
            tokens = _phone_tokens(p.phone)
            if s_phone in tokens:
                return p
                
    return None

def search_all_fields(query: str, data: "CpdData") -> tuple[Participant | None, list[str]]:
    """Search across all participant fields (ID, Phone, Name, Email, Dept)."""
    q = query.strip().lower()
    if not q:
        return None, []
        
    # 1. Try strict ID/Phone match first
    p_exact = find_participant_by_secret(data.participants, query)
    if p_exact:
        return p_exact, []
        
    # 2. Check for substring match in ANY participant field
    matches = []
    q_norm = normalize_name(query)
    
    for p in data.participants:
        # Collect all fields
        fields = [
            p.participant_id, p.name, p.khmer_name, 
            p.profession, p.department, p.email, p.phone
        ]
        text_to_search = " ".join([str(f) for f in fields if f]).lower()
        norm_text = normalize_name(text_to_search)
        
        if q in text_to_search or (q_norm and q_norm in norm_text):
            # Record the primary display name for this matched participant
            matches.append(p.name or p.khmer_name or p.participant_id)
            
    # Deduplicate matches
    matches = list(dict.fromkeys([m for m in matches if m]))
    
    # 3. If no matches in participants, fallback to fuzzy name search on all data (including trainings/certs)
    if not matches:
        chosen, shortlist, _auto = resolve_participant(query, data.all_names(), data.participants)
        if chosen:
            return chosen, []
        return None, shortlist
        
    # 4. If we found matches via substring in fields
    if len(matches) == 1:
        # Find the actual participant object for this name
        p_name = matches[0]
        # Resolve it fully (could be from data.participants)
        p_resolved = exact_participant(data.participants, p_name)
        if p_resolved:
            return p_resolved, []
        return Participant(participant_id="", name=p_name), []
        
    return None, matches[:10]  # Limit to 10 choices