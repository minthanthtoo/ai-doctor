from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple
from uuid import UUID, uuid4

from ai_doctor.auth import Principal
from ai_doctor.capabilities.advice import (
    render_approved_prescription_advice,
    render_patient_advice,
    render_reviewed_advice_plan,
)
from ai_doctor.capabilities.diagnosis import generate_diagnosis_support
from ai_doctor.capabilities.prescribing import (
    ProtocolRepository,
    approve_prescription_draft,
    build_prescription_draft,
)
from ai_doctor.capabilities.triage import assess_triage
from ai_doctor.domain.models import (
    CapabilityName,
    CaseCreate,
    CaseCreated,
    ClinicalDecision,
    PatientAdvice,
    PatientSnapshot,
    ReviewDisposition,
    ReviewRequest,
    SafetyDecision,
    SafetyStatus,
    UrgencyLevel,
    UserRole,
)
from ai_doctor.models.gateway import DiagnosisModelGateway
from ai_doctor.safety.policy import SafetyGate
from ai_doctor.storage.sqlite import SqliteRepository


class ClinicalWorkflowError(ValueError):
    pass


_CLINICAL_REVIEW_ROLES = {
    UserRole.PHYSICIAN,
    UserRole.PHARMACIST,
    UserRole.NURSE,
}

_GENERAL_ADVICE_AUTHOR_ROLES = {UserRole.PHYSICIAN, UserRole.NURSE}


class ClinicalOrchestrator:
    def __init__(
        self,
        repository: SqliteRepository,
        safety_gate: Optional[SafetyGate] = None,
        protocol_repository: Optional[ProtocolRepository] = None,
        diagnosis_model_gateway: Optional[DiagnosisModelGateway] = None,
        emergency_service_label: str = "local emergency services",
    ) -> None:
        self.repository = repository
        self.safety_gate = safety_gate or SafetyGate()
        self.protocol_repository = protocol_repository or ProtocolRepository.from_file()
        # This optional, untrusted component can only augment a deterministic
        # diagnostic baseline after triage and policy authorization.
        self.diagnosis_model_gateway = diagnosis_model_gateway
        self.emergency_service_label = emergency_service_label

    def create_case(self, request: CaseCreate, principal: Principal) -> CaseCreated:
        case_id = uuid4()
        requested = self._normalized_capabilities(request.requested_capabilities)
        decision = self._build_decision(
            case_id=case_id,
            snapshot=request.snapshot,
            requested_capabilities=requested,
            principal=principal,
        )
        self.repository.create_case(
            case_id=case_id,
            snapshot=request.snapshot,
            decision=decision,
            actor_id=principal.user_id,
            actor_role=principal.role.value,
        )
        return CaseCreated(case_id=case_id, decision=decision)

    def get_case(self, case_id: UUID) -> Tuple[PatientSnapshot, ClinicalDecision]:
        return self.repository.get_case(case_id)

    def add_prescription_draft(
        self, case_id: UUID, protocol_id: str, principal: Principal
    ) -> ClinicalDecision:
        snapshot, decision = self.repository.get_case(case_id)
        gate = self.safety_gate.evaluate(
            CapabilityName.PRESCRIPTION_DRAFT,
            snapshot,
            principal.role,
            "prescription_draft",
            "display_for_review",
            emergency_priority=decision.triage.urgency,
        )
        capability_safety = dict(decision.capability_safety)
        capability_safety[CapabilityName.PRESCRIPTION_DRAFT.value] = gate
        releases = dict(decision.capability_releases)
        releases.update(
            self.safety_gate.registry.release_versions([CapabilityName.PRESCRIPTION_DRAFT])
        )
        provenance = dict(decision.capability_provenance)
        provenance.update(
            self.safety_gate.registry.provenance_for([CapabilityName.PRESCRIPTION_DRAFT])
        )

        if gate.status != SafetyStatus.ALLOW_REVIEW:
            updated = decision.model_copy(
                update={
                    "safety": gate,
                    "capability_safety": capability_safety,
                    "capability_releases": releases,
                    "capability_provenance": provenance,
                }
            )
        else:
            draft = build_prescription_draft(snapshot, protocol_id, self.protocol_repository)
            draft_safety = gate
            if draft.status == "blocked":
                draft_safety = SafetyDecision(
                    status=SafetyStatus.BLOCK,
                    reasons=["Prescription protocol evaluation was blocked."],
                    hard_blocks=[*draft.hard_blocks, *draft.missing_inputs],
                    required_actions=[
                        "Resolve every block and re-run an approved protocol before review."
                    ],
                )
                capability_safety[CapabilityName.PRESCRIPTION_DRAFT.value] = draft_safety
            updated = decision.model_copy(
                update={
                    "prescription_draft": draft,
                    "safety": draft_safety,
                    "capability_safety": capability_safety,
                    "capability_releases": releases,
                    "capability_provenance": provenance,
                    "review_status": "pending",
                }
            )

        # Every clinical mutation is a new immutable decision version. This is
        # also the compare-and-swap token used to reject concurrent stale writes.
        updated = updated.model_copy(
            update={"decision_id": uuid4(), "created_at": datetime.now(timezone.utc)}
        )

        self.repository.update_decision(
            case_id=case_id,
            decision=updated,
            event_type="prescription_draft.evaluated",
            actor_id=principal.user_id,
            actor_role=principal.role.value,
            event_payload={
                "decision_id": str(updated.decision_id),
                "protocol_id": protocol_id,
                "draft_status": (
                    updated.prescription_draft.status
                    if updated.prescription_draft is not None
                    else "not_generated"
                ),
                "safety_status": updated.safety.status.value,
            },
            expected_snapshot_id=snapshot.snapshot_id,
            expected_decision_id=decision.decision_id,
        )
        return updated

    def review_case(
        self, case_id: UUID, review: ReviewRequest, principal: Principal
    ) -> ClinicalDecision:
        if principal.role not in _CLINICAL_REVIEW_ROLES:
            raise PermissionError("an authorized clinical reviewer is required")
        snapshot, decision = self.repository.get_case(case_id)

        if review.disposition == ReviewDisposition.AMEND:
            if review.advice_plan is not None:
                raise ClinicalWorkflowError(
                    "advice_plan must be reviewed after the amended case is reassessed"
                )
            return self._amend_and_reassess(
                case_id=case_id,
                snapshot=snapshot,
                decision=decision,
                review=review,
                principal=principal,
            )

        if review.disposition == ReviewDisposition.DEFER:
            if review.follow_up_owner is None or review.follow_up_due_at is None:
                raise ClinicalWorkflowError("defer requires a named follow-up owner and due time")
            if review.follow_up_due_at <= datetime.now(timezone.utc):
                raise ClinicalWorkflowError("follow-up due time must be in the future")

        if review.advice_plan is not None:
            if review.disposition != ReviewDisposition.ACKNOWLEDGE:
                raise ClinicalWorkflowError(
                    "advice_plan is permitted only with an acknowledge disposition"
                )
            if principal.role not in _GENERAL_ADVICE_AUTHOR_ROLES:
                raise PermissionError(
                    "only an authorized physician or nurse may release a general advice plan"
                )

        prescription = decision.prescription_draft
        if review.disposition == ReviewDisposition.APPROVE_DRAFT:
            if principal.role != UserRole.PHYSICIAN:
                raise PermissionError(
                    "this preclinical capability registry permits physician approval only"
                )
            if prescription is None:
                raise ClinicalWorkflowError("no prescription draft exists to approve")
            # Approval is a high-consequence transition.  Re-run deterministic
            # triage and the released prescription envelope immediately before
            # approval; compare-and-swap persistence below prevents a concurrent
            # amendment from invalidating this check before commit.
            current_triage = assess_triage(snapshot, self.emergency_service_label)
            approval_gate = self.safety_gate.evaluate(
                CapabilityName.PRESCRIPTION_DRAFT,
                snapshot,
                principal.role,
                "prescription_draft",
                "display_for_review",
                emergency_priority=current_triage.urgency,
            )
            if current_triage.urgency == UrgencyLevel.EMERGENCY_NOW:
                raise ClinicalWorkflowError(
                    "prescription approval is blocked because emergency triage takes priority"
                )
            if approval_gate.status != SafetyStatus.ALLOW_REVIEW:
                raise ClinicalWorkflowError(
                    "prescription approval is outside the current released safety envelope"
                )
            if current_triage.model_dump(mode="json") != decision.triage.model_dump(mode="json"):
                raise ClinicalWorkflowError(
                    "case triage changed; reassess the case before approving a prescription draft"
                )
            prescription = approve_prescription_draft(
                prescription, principal.user_id, principal.role
            )

        review_status = {
            ReviewDisposition.ACKNOWLEDGE: "reviewed",
            ReviewDisposition.REJECT: "rejected",
            ReviewDisposition.DEFER: "deferred",
            ReviewDisposition.APPROVE_DRAFT: "reviewed",
        }.get(review.disposition, "reviewed")
        reviewed = decision.model_copy(
            update={
                "decision_id": uuid4(),
                "created_at": datetime.now(timezone.utc),
                "prescription_draft": prescription,
                "review_status": review_status,
                "review_disposition": review.disposition,
                "reviewed_by": principal.user_id,
                "reviewed_at": datetime.now(timezone.utc),
            }
        )

        if review.disposition == ReviewDisposition.APPROVE_DRAFT:
            advice = render_approved_prescription_advice(reviewed)
        elif review.advice_plan is not None:
            advice = render_reviewed_advice_plan(reviewed, review.advice_plan)
        else:
            advice = render_patient_advice(reviewed)
        reviewed = reviewed.model_copy(update={"patient_advice": advice})

        self.repository.update_decision(
            case_id=case_id,
            decision=reviewed,
            event_type="decision.reviewed",
            actor_id=principal.user_id,
            actor_role=principal.role.value,
            event_payload={
                "decision_id": str(reviewed.decision_id),
                "disposition": review.disposition.value,
                "rationale": review.rationale,
                "advice_plan_supplied": review.advice_plan is not None,
                "follow_up_owner": review.follow_up_owner,
                "follow_up_due_at": (
                    review.follow_up_due_at.isoformat() if review.follow_up_due_at else None
                ),
            },
            expected_snapshot_id=snapshot.snapshot_id,
            expected_decision_id=decision.decision_id,
        )
        return reviewed

    def get_patient_advice(self, case_id: UUID, principal: Principal) -> PatientAdvice:
        snapshot, decision = self.repository.get_case(case_id)
        if decision.triage.urgency == UrgencyLevel.EMERGENCY_NOW:
            gate = self.safety_gate.evaluate(
                CapabilityName.EMERGENCY_TRIAGE,
                snapshot,
                principal.role,
                "emergency_instruction",
                "display_triage",
                emergency_priority=decision.triage.urgency,
            )
            if gate.status != SafetyStatus.ESCALATE:
                return PatientAdvice(
                    status="blocked_by_safety_gate",
                    summary="Emergency advice is unavailable to this role.",
                    source_decision_id=decision.decision_id,
                    clinician_approval_required=True,
                )
            advice = render_patient_advice(decision)
        else:
            gate = self.safety_gate.evaluate(
                CapabilityName.PATIENT_ADVICE,
                snapshot,
                principal.role,
                "patient_advice",
                "display_for_review",
                emergency_priority=decision.triage.urgency,
            )
            if gate.status not in {SafetyStatus.ALLOW_REVIEW, SafetyStatus.ESCALATE}:
                return PatientAdvice(
                    status="blocked_by_safety_gate",
                    summary="Patient advice is unavailable for this case.",
                    source_decision_id=decision.decision_id,
                    clinician_approval_required=True,
                )
            if (
                decision.prescription_draft is not None
                and decision.prescription_draft.status == "clinician_approved_draft"
            ):
                advice = render_approved_prescription_advice(decision)
            elif decision.patient_advice is not None:
                advice = decision.patient_advice
            else:
                advice = render_patient_advice(decision)

        self.repository.append_event(
            case_id=case_id,
            event_type="patient_advice.viewed",
            actor_id=principal.user_id,
            actor_role=principal.role.value,
            payload={
                "decision_id": str(decision.decision_id),
                "advice_id": str(advice.advice_id),
                "advice_status": advice.status,
            },
        )
        return advice

    def _build_decision(
        self,
        *,
        case_id: UUID,
        snapshot: PatientSnapshot,
        requested_capabilities: Sequence[CapabilityName],
        principal: Principal,
    ) -> ClinicalDecision:
        triage = assess_triage(snapshot, self.emergency_service_label)
        requested: Set[CapabilityName] = set(requested_capabilities)
        requested.add(CapabilityName.EMERGENCY_TRIAGE)
        capability_safety: Dict[str, SafetyDecision] = {}

        triage_output = (
            "emergency_instruction"
            if triage.urgency == UrgencyLevel.EMERGENCY_NOW
            else "triage_assessment"
        )
        triage_gate = self.safety_gate.evaluate(
            CapabilityName.EMERGENCY_TRIAGE,
            snapshot,
            principal.role,
            triage_output,
            "display_triage",
            emergency_priority=triage.urgency,
        )
        capability_safety[CapabilityName.EMERGENCY_TRIAGE.value] = triage_gate

        diagnosis = None
        if CapabilityName.DIAGNOSIS_SUPPORT in requested:
            diagnosis_gate = self.safety_gate.evaluate(
                CapabilityName.DIAGNOSIS_SUPPORT,
                snapshot,
                principal.role,
                "diagnostic_assessment",
                "display_for_review",
                emergency_priority=triage.urgency,
            )
            capability_safety[CapabilityName.DIAGNOSIS_SUPPORT.value] = diagnosis_gate
            if diagnosis_gate.status == SafetyStatus.ALLOW_REVIEW:
                diagnosis = generate_diagnosis_support(snapshot, triage)
                if self.diagnosis_model_gateway is not None:
                    diagnosis = self.diagnosis_model_gateway.augment(snapshot, triage, diagnosis)

        if CapabilityName.PATIENT_ADVICE in requested:
            advice_gate = self.safety_gate.evaluate(
                CapabilityName.PATIENT_ADVICE,
                snapshot,
                principal.role,
                "patient_advice",
                "display_for_review",
                emergency_priority=triage.urgency,
            )
            capability_safety[CapabilityName.PATIENT_ADVICE.value] = advice_gate

        if CapabilityName.PRESCRIPTION_DRAFT in requested:
            capability_safety[CapabilityName.PRESCRIPTION_DRAFT.value] = SafetyDecision(
                status=SafetyStatus.REQUEST_MORE_DATA,
                reasons=["A released protocol identifier is required."],
                required_actions=["Use the prescription-draft endpoint with an approved protocol."],
            )

        overall = self._overall_safety(triage.urgency, capability_safety)
        releases = self.safety_gate.registry.release_versions(requested)
        provenance = self.safety_gate.registry.provenance_for(requested)
        decision = ClinicalDecision(
            case_id=case_id,
            snapshot_id=snapshot.snapshot_id,
            triage=triage,
            diagnosis=diagnosis,
            safety=overall,
            capability_safety=capability_safety,
            capability_releases=releases,
            capability_provenance=provenance,
        )
        if (
            triage.urgency == UrgencyLevel.EMERGENCY_NOW
            and triage_gate.status == SafetyStatus.ESCALATE
        ):
            decision = decision.model_copy(
                update={"patient_advice": render_patient_advice(decision)}
            )
        return decision

    def _amend_and_reassess(
        self,
        *,
        case_id: UUID,
        snapshot: PatientSnapshot,
        decision: ClinicalDecision,
        review: ReviewRequest,
        principal: Principal,
    ) -> ClinicalDecision:
        if not review.amendments:
            raise ClinicalWorkflowError("amend requires at least one changed field")
        protected = {
            "snapshot_id",
            "patient_ref",
            "encounter_ref",
            "created_at",
        }
        invalid = protected.intersection(review.amendments)
        if invalid:
            raise ClinicalWorkflowError(
                "amend cannot change protected fields: " + ", ".join(sorted(invalid))
            )
        allowed = {
            "age_years",
            "sex_at_birth",
            "pregnancy_status",
            "symptoms",
            "medications",
            "medication_list_confirmed",
            "allergies",
            "allergy_status_confirmed",
            "conditions",
            "labs",
            "vitals",
            "free_text_context",
            "confirmed_by_clinician",
        }
        unknown = set(review.amendments).difference(allowed)
        if unknown:
            raise ClinicalWorkflowError(
                "unsupported amendment fields: " + ", ".join(sorted(unknown))
            )

        payload = snapshot.model_dump(mode="python")
        payload.update(review.amendments)
        payload.update(
            {
                "snapshot_id": uuid4(),
                "created_at": datetime.now(timezone.utc),
                "confirmed_by_clinician": True,
            }
        )
        successor = PatientSnapshot.model_validate(payload)
        requested = [CapabilityName(key) for key in decision.capability_releases]
        reassessed = self._build_decision(
            case_id=case_id,
            snapshot=successor,
            requested_capabilities=requested,
            principal=principal,
        )
        self.repository.replace_case_state(
            case_id=case_id,
            snapshot=successor,
            decision=reassessed,
            event_type="decision.amended_and_reassessed",
            actor_id=principal.user_id,
            actor_role=principal.role.value,
            event_payload={
                "predecessor_snapshot_id": str(snapshot.snapshot_id),
                "successor_snapshot_id": str(successor.snapshot_id),
                "predecessor_decision_id": str(decision.decision_id),
                "successor_decision_id": str(reassessed.decision_id),
                "amended_fields": sorted(review.amendments),
                "rationale": review.rationale,
            },
            expected_snapshot_id=snapshot.snapshot_id,
            expected_decision_id=decision.decision_id,
        )
        return reassessed

    @staticmethod
    def _normalized_capabilities(
        capabilities: Iterable[CapabilityName],
    ) -> List[CapabilityName]:
        result: List[CapabilityName] = []
        seen: Set[CapabilityName] = set()
        for capability in capabilities:
            if capability not in seen:
                seen.add(capability)
                result.append(capability)
        return result

    @staticmethod
    def _overall_safety(
        urgency: UrgencyLevel,
        capability_safety: Dict[str, SafetyDecision],
    ) -> SafetyDecision:
        if urgency == UrgencyLevel.EMERGENCY_NOW:
            return SafetyDecision(
                status=SafetyStatus.ESCALATE,
                reasons=["Emergency triage takes priority over all other capabilities."],
                required_actions=[
                    "Display the emergency instruction and seek emergency services now."
                ],
            )
        if urgency == UrgencyLevel.INSUFFICIENT_DATA:
            return SafetyDecision(
                status=SafetyStatus.REQUEST_MORE_DATA,
                reasons=["Triage inputs are incomplete; absence of a red flag is not reassurance."],
                required_actions=[
                    "Obtain the missing triage inputs or arrange clinical assessment."
                ],
            )
        non_triage = [
            value
            for key, value in capability_safety.items()
            if key != CapabilityName.EMERGENCY_TRIAGE.value
        ]
        if non_triage and all(value.status == SafetyStatus.BLOCK for value in non_triage):
            blocks = [block for value in non_triage for block in value.hard_blocks]
            return SafetyDecision(
                status=SafetyStatus.BLOCK,
                reasons=["Every requested non-triage capability was blocked."],
                hard_blocks=blocks,
            )
        return SafetyDecision(
            status=SafetyStatus.ALLOW_REVIEW,
            reasons=["Available outputs may be displayed within their review boundaries."],
            required_actions=["Follow each capability-specific review requirement."],
        )
