"""Bounded, non-authoritative syndromic differential support."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Set

from ai_doctor.capabilities.clinical_text import clinical_texts, contains_affirmed_term
from ai_doctor.domain.models import (
    DiagnosticAssessment,
    DiagnosticHypothesis,
    EvidenceRef,
    LikelihoodBand,
    PatientSnapshot,
    TriageAssessment,
    UrgencyLevel,
)

_RULE_PATH = Path(__file__).resolve().parents[1] / "knowledge" / "diagnosis_rules.json"


def _rules() -> Dict[str, Any]:
    with _RULE_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def _text(snapshot: PatientSnapshot) -> str:
    return " . ".join(clinical_texts(snapshot))


def _missing_basics(snapshot: PatientSnapshot) -> List[str]:
    missing = []
    if snapshot.age_years is None:
        missing.append("age")
    if snapshot.vitals is None:
        missing.append("vital signs")
    if snapshot.pregnancy_status.value == "unknown":
        missing.append("pregnancy status when relevant")
    return missing


def generate_diagnosis_support(
    snapshot: PatientSnapshot, triage: TriageAssessment
) -> DiagnosticAssessment:
    """Generate at most five pattern hypotheses; never establishes a diagnosis."""
    rules = _rules()
    text = _text(snapshot)
    matched = [
        pattern for pattern in rules["patterns"] if contains_affirmed_term(text, pattern["terms"])
    ]
    missing = _missing_basics(snapshot)
    hypotheses: List[DiagnosticHypothesis] = []
    dangerous: List[str] = []
    used: Set[str] = set()

    for pattern in matched:
        for candidate in pattern["hypotheses"]:
            name = candidate["name"]
            if name in used or len(hypotheses) >= rules["maximum_hypotheses"]:
                continue
            used.add(name)
            is_dangerous = bool(candidate["dangerous"])
            if is_dangerous:
                dangerous.append(name)
            hypotheses.append(
                DiagnosticHypothesis(
                    name=name,
                    likelihood=LikelihoodBand.UNDETERMINED,
                    evidence_for=[
                        "Configured symptom pattern '%s' was present." % pattern["problem"]
                    ],
                    evidence_against=[
                        "Available input is insufficient to confirm or exclude this possibility."
                    ],
                    missing_information=list(missing)
                    + ["targeted history and physical examination"],
                    dangerous_if_missed=is_dangerous,
                    evidence_refs=[
                        EvidenceRef(
                            evidence_id="PATTERN_%s" % pattern["id"].upper(),
                            title="Preclinical syndromic pattern: %s" % pattern["problem"],
                            source_version=rules["release"],
                            applies_to=[name],
                        )
                    ],
                )
            )

    representations = [pattern["problem"] for pattern in matched]
    if representations:
        representation = "Reported %s" % "; ".join(representations[:2])
    else:
        representation = (
            "No supported syndromic pattern was identified from the limited structured input."
        )

    limitations = [
        rules["coverage"],
        "This output is decision support only; it does not establish a diagnosis or recommend treatment.",
    ]
    if triage.urgency == UrgencyLevel.EMERGENCY_NOW:
        limitations.append("Emergency triage takes priority over differential generation.")
    if not matched:
        limitations.append(
            "No pattern matched; absence of a match does not exclude illness or emergency conditions."
        )

    next_information = [
        "Clarify onset, progression, severity, associated symptoms, and relevant exposures.",
        "Obtain clinician assessment and a targeted physical examination.",
    ]
    if missing:
        next_information.insert(0, "Obtain missing inputs: %s." % ", ".join(missing))

    return DiagnosticAssessment(
        problem_representation=representation,
        hypotheses=hypotheses,
        dangerous_alternatives=dangerous,
        next_information=next_information,
        limitations=limitations,
        model_release=rules["release"],
        authoritative=False,
    )


diagnose_snapshot = generate_diagnosis_support
generate_differential = generate_diagnosis_support
