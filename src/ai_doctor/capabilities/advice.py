"""Fixed rendering of patient advice from structured, reviewed decisions."""

from __future__ import annotations

from typing import List, Optional

from ai_doctor.domain.models import (
    ClinicalDecision,
    PatientAdvice,
    ReviewDisposition,
    ReviewedAdvicePlan,
    UrgencyLevel,
)

_ACCEPTED_REVIEW_DISPOSITIONS = {
    ReviewDisposition.ACKNOWLEDGE,
    ReviewDisposition.AMEND,
    ReviewDisposition.APPROVE_DRAFT,
}


def render_patient_advice(decision: ClinicalDecision) -> PatientAdvice:
    """Render only already-authoritative triage content.

    Emergency triage is deliberately the sole route which can render before a
    clinician review.  Non-emergency advice must be based on a recorded clinician
    disposition.  The renderer does not consult a model or add a medical claim.
    """

    triage = decision.triage
    emergency = triage.urgency == UrgencyLevel.EMERGENCY_NOW
    if not emergency and not _clinician_reviewed(decision):
        return PatientAdvice(
            status="blocked_pending_clinician_review",
            summary="Patient advice is unavailable until a clinician reviews this decision.",
            source_decision_id=decision.decision_id,
            clinician_approval_required=True,
        )

    actions = _unique(
        [
            finding.recommended_response
            for finding in triage.findings
            if finding.recommended_response
        ]
    )
    warning_signs = _unique([finding.title for finding in triage.findings if finding.title])
    emergency_instruction = triage.emergency_instruction if emergency else None
    if emergency and emergency_instruction:
        actions = _unique([emergency_instruction, *actions])
    summary = _summary(triage.coverage_statement, emergency_instruction, actions)
    return PatientAdvice(
        status="emergency_preapproved" if emergency else "clinician_reviewed",
        summary=summary,
        actions=actions,
        warning_signs=warning_signs,
        emergency_instruction=emergency_instruction,
        source_decision_id=decision.decision_id,
        clinician_approval_required=False,
    )


def render_reviewed_advice_plan(
    decision: ClinicalDecision, plan: ReviewedAdvicePlan
) -> PatientAdvice:
    """Copy a bounded clinician-authored care plan after recorded review."""

    if not _clinician_reviewed(decision):
        return PatientAdvice(
            status="blocked_pending_clinician_review",
            summary="Patient advice is unavailable until a clinician reviews this decision.",
            source_decision_id=decision.decision_id,
            clinician_approval_required=True,
        )
    return PatientAdvice(
        status="clinician_authored_advice",
        summary=plan.summary,
        actions=_unique(plan.actions),
        avoid=_unique(plan.avoid),
        warning_signs=_unique(plan.warning_signs),
        follow_up=_unique(plan.follow_up),
        source_decision_id=decision.decision_id,
        clinician_approval_required=False,
    )


def render_approved_prescription_advice(decision: ClinicalDecision) -> PatientAdvice:
    """Render medication instructions only from a clinician-approved draft.

    This renderer copies approved structured protocol content. It does not infer
    dosing, indication, monitoring, warnings, or a diagnosis.
    """

    draft = decision.prescription_draft
    if draft is None or draft.status != "clinician_approved_draft" or not draft.approved_by:
        return PatientAdvice(
            status="blocked_pending_prescriber_approval",
            summary="Medication instructions are unavailable until an authorized prescriber approves the draft.",
            source_decision_id=decision.decision_id,
            clinician_approval_required=True,
        )

    actions: List[str] = []
    warning_signs: List[str] = []
    follow_up: List[str] = []
    for item in draft.items:
        duration = " for " + item.duration if item.duration else ""
        actions.append(
            "Take {name} {dose} by {route}, {frequency}{duration}, for {indication}.".format(
                name=item.medication_name,
                dose=item.dose,
                route=item.route,
                frequency=item.frequency,
                duration=duration,
                indication=item.indication,
            )
        )
        warning_signs.extend(item.warnings)
        follow_up.extend(item.monitoring)

    return PatientAdvice(
        status="clinician_approved_prescription_advice",
        summary="Follow the medication instructions approved by your prescriber.",
        actions=_unique(actions),
        warning_signs=_unique(warning_signs),
        follow_up=_unique(follow_up),
        source_decision_id=decision.decision_id,
        clinician_approval_required=False,
    )


def _clinician_reviewed(decision: ClinicalDecision) -> bool:
    return (
        bool(decision.reviewed_by)
        and decision.reviewed_at is not None
        and decision.review_disposition in _ACCEPTED_REVIEW_DISPOSITIONS
    )


def _summary(coverage: str, emergency_instruction: Optional[str], actions: List[str]) -> str:
    # These strings were already authored by the approved structured decision.
    if emergency_instruction:
        return emergency_instruction
    if actions:
        return actions[0]
    return coverage


def _unique(values: List[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
