from __future__ import annotations

import re
from typing import Iterable, List

from ai_doctor.domain.models import PatientSnapshot

_NEGATION_PREFIX = re.compile(
    r"(?:\bno|\bdenies|\bdenied|\bwithout|\bnot experiencing|\bnegative for)\s+$",
    re.IGNORECASE,
)


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
            if _NEGATION_PREFIX.search(local_prefix):
                continue
            return True
    return False
