from __future__ import annotations

import re
from typing import Iterable, List

from ai_doctor.domain.models import PatientSnapshot

# Strict rule (original behavior): a negator immediately before the term.
_NEGATION_PREFIX = re.compile(
    r"(?:\bno|\bnever|\bnot|\bdenies|\bdenied|\bwithout|\bnot experiencing|\bnegative for)\s+$"
)
# Coordinate extension (NegEx-lite): a negator followed by up to two filler
# words, covering lists such as "no weakness or slurred speech".
_NEGATION_COORD = re.compile(
    r"(?:\bno|\bnever|\bnot|\bdenies|\bdenied|\bwithout|\bnegative for)"
    r"(\s+(?:[\w'-]+\s+){0,2})$"
)
# Contrast/temporal breakers: if they appear between negator and term, the
# negator does not govern the term ("no relief until chest pain started").
_COORD_BREAK = re.compile(
    r"\b(?:but|however|except|until|after|before|when|while|since|then|because)\b",
)


def _is_negated_prefix(prefix: str) -> bool:
    """Fail-closed negation scope check.

    The strict rule short-circuits first, preserving historical behavior;
    the coordinate extension only widens scope across short coordinated
    phrases and refuses when any breaker word intervenes.
    """
    if _NEGATION_PREFIX.search(prefix):
        return True
    match = _NEGATION_COORD.search(prefix)
    return bool(match) and not bool(_COORD_BREAK.search(match.group(1)))


def clinical_texts(snapshot: PatientSnapshot) -> List[str]:
    texts: List[str] = []
    for symptom in snapshot.symptoms:
        # ``attributes`` is an open, user-controlled mapping. It cannot turn an
        # asserted structured symptom name into a negation. A future typed
        # assertion-status field may support that distinction explicitly.
        values = [symptom.name, symptom.onset or "", symptom.duration or ""]
        values.extend(str(value) for key, value in symptom.attributes.items() if key != "negated")
        texts.append(" ".join(values).lower())
    if snapshot.free_text_context:
        texts.append(snapshot.free_text_context.lower())
    return texts


def contains_affirmed_term(text: str, terms: Iterable[str]) -> bool:
    for term in terms:
        pattern = re.compile(r"(?<!\w)" + re.escape(term.lower()) + r"(?!\w)")
        for match in pattern.finditer(text.lower()):
            prefix = text[max(0, match.start() - 40) : match.start()]
            # Use text after the latest strong punctuation as the local clause.
            local_prefix = re.split(r"[.;!?\n]", prefix)[-1]
            if _is_negated_prefix(local_prefix):
                continue
            return True
    return False
