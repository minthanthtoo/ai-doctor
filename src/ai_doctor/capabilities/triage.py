"""Deterministic, preclinical emergency-triage screening.

This module deliberately detects only explicit, narrow red flags.  A lack of a
finding is never evidence that a patient is safe.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Set

from ai_doctor.capabilities.clinical_text import clinical_texts, contains_affirmed_term
from ai_doctor.domain.models import (
    PatientSnapshot,
    Severity,
    TriageAssessment,
    TriageFinding,
    UrgencyLevel,
)

_RULE_PATH = Path(__file__).resolve().parents[1] / "knowledge" / "triage_rules.json"


def _rules() -> Dict[str, Any]:
    with _RULE_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def _fact_ref(kind: str, position: int) -> str:
    return "%s[%d]" % (kind, position)


def _emergency_finding(rule_id: str, title: str, refs: List[str]) -> TriageFinding:
    return TriageFinding(
        rule_id=rule_id,
        urgency=UrgencyLevel.EMERGENCY_NOW,
        severity=Severity.CRITICAL,
        title=title,
        rationale="A configured emergency red flag was present in the available input.",
        trigger_fact_refs=refs,
        recommended_response="Seek immediate in-person emergency assessment.",
    )


def assess_triage(
    snapshot: PatientSnapshot,
    emergency_service_label: str = "local emergency services",
) -> TriageAssessment:
    """Return a deterministic, conservative triage screen for one snapshot."""
    rules = _rules()
    findings: List[TriageFinding] = []
    seen: Set[str] = set()
    texts = clinical_texts(snapshot)

    for entry in rules["red_flag_symptoms"]:
        refs: List[str] = []
        for index, text in enumerate(texts):
            if contains_affirmed_term(text, entry["terms"]):
                refs.append(_fact_ref("symptom_or_context", index))
        if refs and entry["id"] not in seen:
            findings.append(
                _emergency_finding("TRIAGE_%s" % entry["id"].upper(), entry["title"], refs)
            )
            seen.add(entry["id"])

    vitals = snapshot.vitals
    if vitals is not None:
        for field, threshold in rules["vital_thresholds"].items():
            value = getattr(vitals, field)
            triggered = value is not None and (
                ("less_than" in threshold and value < threshold["less_than"])
                or ("less_than_or_equal" in threshold and value <= threshold["less_than_or_equal"])
                or ("greater_than" in threshold and value > threshold["greater_than"])
                or (
                    "greater_than_or_equal" in threshold
                    and value >= threshold["greater_than_or_equal"]
                )
            )
            if triggered:
                findings.append(
                    _emergency_finding(
                        "TRIAGE_VITAL_%s" % field.upper(), threshold["title"], ["vitals.%s" % field]
                    )
                )

    missing: List[str] = []
    if not snapshot.symptoms and not snapshot.free_text_context:
        missing.append("presenting symptoms or clinical context")
    if vitals is None:
        missing.append("vital signs")
    else:
        essential = (
            "heart_rate_bpm",
            "respiratory_rate_bpm",
            "systolic_bp_mmhg",
            "oxygen_saturation_percent",
            "temperature_c",
        )
        missing.extend("vitals.%s" % key for key in essential if getattr(vitals, key) is None)
    if snapshot.age_years is None:
        missing.append("age")
    elif snapshot.age_years < 18:
        missing.append("validated pediatric triage rule set")
    if snapshot.pregnancy_status.value == "unknown":
        missing.append("pregnancy status")

    if findings:
        urgency = UrgencyLevel.EMERGENCY_NOW
        instruction = rules["emergency_instruction"].replace(
            "local emergency services", emergency_service_label
        )
    elif not snapshot.symptoms and not snapshot.free_text_context or missing:
        urgency = UrgencyLevel.INSUFFICIENT_DATA
        instruction = None
    else:
        urgency = UrgencyLevel.ROUTINE
        instruction = None

    return TriageAssessment(
        urgency=urgency,
        findings=findings,
        missing_inputs=missing,
        emergency_instruction=instruction,
        coverage_statement=rules["coverage"],
        rule_release=rules["release"],
    )


# Explicit aliases make the capability convenient to call from an orchestrator.
triage_snapshot = assess_triage
run_triage = assess_triage
