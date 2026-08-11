from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class SexAtBirth(str, Enum):
    FEMALE = "female"
    MALE = "male"
    INTERSEX = "intersex"
    UNKNOWN = "unknown"


class PregnancyStatus(str, Enum):
    PREGNANT = "pregnant"
    POSSIBLY_PREGNANT = "possibly_pregnant"
    NOT_PREGNANT = "not_pregnant"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


class VerificationStatus(str, Enum):
    SOURCE_VERIFIED = "source_verified"
    CLINICIAN_VERIFIED = "clinician_verified"
    PATIENT_REPORTED = "patient_reported"
    INFERRED_CANDIDATE = "inferred_candidate"
    CONFLICTED = "conflicted"


class UrgencyLevel(str, Enum):
    EMERGENCY_NOW = "emergency_now"
    URGENT_SAME_DAY = "urgent_same_day"
    SOON_24_48_HOURS = "soon_24_48_hours"
    ROUTINE = "routine"
    INSUFFICIENT_DATA = "insufficient_data"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    INFORMATIONAL = "informational"


class LikelihoodBand(str, Enum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    UNDETERMINED = "undetermined"


class SafetyStatus(str, Enum):
    ALLOW_REVIEW = "allow_review"
    REQUEST_MORE_DATA = "request_more_data"
    ESCALATE = "escalate"
    BLOCK = "block"
    OUT_OF_SCOPE = "out_of_scope"


class ReviewDisposition(str, Enum):
    ACKNOWLEDGE = "acknowledge"
    REJECT = "reject"
    AMEND = "amend"
    DEFER = "defer"
    APPROVE_DRAFT = "approve_draft"


class UserRole(str, Enum):
    PHYSICIAN = "physician"
    PHARMACIST = "pharmacist"
    NURSE = "nurse"
    CLINICAL_SAFETY_OFFICER = "clinical_safety_officer"
    PATIENT = "patient"
    SYSTEM = "system"


class CapabilityName(str, Enum):
    EMERGENCY_TRIAGE = "emergency_triage"
    DIAGNOSIS_SUPPORT = "diagnosis_support"
    PRESCRIPTION_DRAFT = "prescription_draft"
    PATIENT_ADVICE = "patient_advice"


class SourceRef(StrictModel):
    source_id: str
    source_type: str
    title: str
    uri: Optional[str] = None
    version: Optional[str] = None
    retrieved_at: datetime = Field(default_factory=utc_now)


class Symptom(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    onset: Optional[str] = Field(default=None, max_length=200)
    duration: Optional[str] = Field(default=None, max_length=200)
    severity_0_to_10: Optional[int] = Field(default=None, ge=0, le=10)
    attributes: Dict[str, Any] = Field(default_factory=dict)
    verification_status: VerificationStatus = VerificationStatus.PATIENT_REPORTED
    source: Optional[SourceRef] = None


class Medication(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    normalized_id: Optional[str] = None
    dose: Optional[str] = None
    route: Optional[str] = None
    frequency: Optional[str] = None
    indication: Optional[str] = None
    status: str = "unknown"
    verification_status: VerificationStatus = VerificationStatus.PATIENT_REPORTED
    source: Optional[SourceRef] = None


class Allergy(StrictModel):
    substance: str = Field(min_length=1, max_length=200)
    reaction: Optional[str] = None
    severity: Optional[Severity] = None
    verification_status: VerificationStatus = VerificationStatus.PATIENT_REPORTED
    source: Optional[SourceRef] = None


class Condition(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    code: Optional[str] = None
    status: str = "active"
    verification_status: VerificationStatus = VerificationStatus.SOURCE_VERIFIED
    source: Optional[SourceRef] = None


class LabResult(StrictModel):
    code: str
    display: str
    value: float
    unit: str
    reference_low: Optional[float] = None
    reference_high: Optional[float] = None
    observed_at: datetime
    verification_status: VerificationStatus = VerificationStatus.SOURCE_VERIFIED
    source: Optional[SourceRef] = None


class VitalSigns(StrictModel):
    observed_at: datetime = Field(default_factory=utc_now)
    heart_rate_bpm: Optional[float] = Field(default=None, ge=0, le=350)
    respiratory_rate_bpm: Optional[float] = Field(default=None, ge=0, le=100)
    systolic_bp_mmhg: Optional[float] = Field(default=None, ge=0, le=350)
    diastolic_bp_mmhg: Optional[float] = Field(default=None, ge=0, le=250)
    oxygen_saturation_percent: Optional[float] = Field(default=None, ge=0, le=100)
    temperature_c: Optional[float] = Field(default=None, ge=25, le=45)
    glucose_mg_dl: Optional[float] = Field(default=None, ge=0, le=3000)
    verification_status: VerificationStatus = VerificationStatus.SOURCE_VERIFIED
    source: Optional[SourceRef] = None


class PatientSnapshot(StrictModel):
    snapshot_id: UUID = Field(default_factory=uuid4)
    patient_ref: str = Field(min_length=1)
    encounter_ref: Optional[str] = None
    age_years: Optional[float] = Field(default=None, ge=0, le=130)
    sex_at_birth: SexAtBirth = SexAtBirth.UNKNOWN
    pregnancy_status: PregnancyStatus = PregnancyStatus.UNKNOWN
    symptoms: List[Symptom] = Field(default_factory=list)
    medications: List[Medication] = Field(default_factory=list)
    medication_list_confirmed: bool = False
    allergies: List[Allergy] = Field(default_factory=list)
    allergy_status_confirmed: bool = False
    conditions: List[Condition] = Field(default_factory=list)
    labs: List[LabResult] = Field(default_factory=list)
    vitals: Optional[VitalSigns] = None
    free_text_context: Optional[str] = Field(default=None, max_length=10000)
    confirmed_by_clinician: bool = False
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def require_some_clinical_context(self) -> "PatientSnapshot":
        if not (self.symptoms or self.medications or self.conditions or self.labs or self.vitals):
            raise ValueError("at least one clinical input is required")
        return self


class EvidenceRef(StrictModel):
    evidence_id: str
    title: str
    source_uri: Optional[str] = None
    source_version: Optional[str] = None
    applies_to: List[str] = Field(default_factory=list)


class RuleTrace(StrictModel):
    rule_id: str
    rule_version: str
    result: str
    trigger_fact_refs: List[str] = Field(default_factory=list)
    missing_inputs: List[str] = Field(default_factory=list)
    evidence_refs: List[EvidenceRef] = Field(default_factory=list)


class TriageFinding(StrictModel):
    rule_id: str
    urgency: UrgencyLevel
    severity: Severity
    title: str
    rationale: str
    trigger_fact_refs: List[str] = Field(default_factory=list)
    recommended_response: str


class TriageAssessment(StrictModel):
    urgency: UrgencyLevel
    findings: List[TriageFinding] = Field(default_factory=list)
    missing_inputs: List[str] = Field(default_factory=list)
    emergency_instruction: Optional[str] = None
    coverage_statement: str
    rule_release: str


class DiagnosticHypothesis(StrictModel):
    name: str
    likelihood: LikelihoodBand
    evidence_for: List[str] = Field(default_factory=list)
    evidence_against: List[str] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    dangerous_if_missed: bool = False
    evidence_refs: List[EvidenceRef] = Field(default_factory=list)


class DiagnosticAssessment(StrictModel):
    problem_representation: str
    hypotheses: List[DiagnosticHypothesis] = Field(default_factory=list)
    dangerous_alternatives: List[str] = Field(default_factory=list)
    next_information: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    model_release: str
    authoritative: bool = False


class PrescriptionItem(StrictModel):
    medication_name: str
    dose: str
    route: str
    frequency: str
    duration: Optional[str] = None
    indication: str
    protocol_id: str
    protocol_version: str
    monitoring: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class PrescriptionDraft(StrictModel):
    draft_id: UUID = Field(default_factory=uuid4)
    status: str = "pending_clinician_review"
    items: List[PrescriptionItem] = Field(default_factory=list)
    hard_blocks: List[str] = Field(default_factory=list)
    missing_inputs: List[str] = Field(default_factory=list)
    protocol_trace: List[RuleTrace] = Field(default_factory=list)
    clinician_approval_required: bool = True
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    executable: bool = False


class PatientAdvice(StrictModel):
    advice_id: UUID = Field(default_factory=uuid4)
    status: str
    audience: str = "patient"
    summary: str
    actions: List[str] = Field(default_factory=list)
    avoid: List[str] = Field(default_factory=list)
    warning_signs: List[str] = Field(default_factory=list)
    follow_up: List[str] = Field(default_factory=list)
    emergency_instruction: Optional[str] = None
    source_decision_id: Optional[UUID] = None
    clinician_approval_required: bool = True


class ReviewedAdvicePlan(StrictModel):
    """Clinician-authored content that can be released as patient advice.

    This object is intentionally structured and bounded. The application copies
    it after an authorized review; it never asks a model to invent or expand it.
    """

    summary: str = Field(min_length=1, max_length=2000)
    actions: List[str] = Field(default_factory=list, max_length=20)
    avoid: List[str] = Field(default_factory=list, max_length=20)
    warning_signs: List[str] = Field(default_factory=list, max_length=20)
    follow_up: List[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def bound_item_lengths(self) -> "ReviewedAdvicePlan":
        for collection in (
            self.actions,
            self.avoid,
            self.warning_signs,
            self.follow_up,
        ):
            if any(not item.strip() or len(item) > 1000 for item in collection):
                raise ValueError("advice list items must contain 1 to 1000 characters")
        return self


class SafetyDecision(StrictModel):
    status: SafetyStatus
    reasons: List[str] = Field(default_factory=list)
    hard_blocks: List[str] = Field(default_factory=list)
    required_actions: List[str] = Field(default_factory=list)


class ClinicalDecision(StrictModel):
    decision_id: UUID = Field(default_factory=uuid4)
    case_id: UUID
    snapshot_id: UUID
    created_at: datetime = Field(default_factory=utc_now)
    triage: TriageAssessment
    diagnosis: Optional[DiagnosticAssessment] = None
    prescription_draft: Optional[PrescriptionDraft] = None
    patient_advice: Optional[PatientAdvice] = None
    safety: SafetyDecision
    capability_safety: Dict[str, SafetyDecision] = Field(default_factory=dict)
    capability_releases: Dict[str, str] = Field(default_factory=dict)
    capability_provenance: Dict[str, Dict[str, str]] = Field(default_factory=dict)
    review_status: str = "pending"
    review_disposition: Optional[ReviewDisposition] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None


class CaseCreate(StrictModel):
    snapshot: PatientSnapshot
    requested_capabilities: List[CapabilityName] = Field(
        default_factory=lambda: [
            CapabilityName.EMERGENCY_TRIAGE,
            CapabilityName.DIAGNOSIS_SUPPORT,
        ]
    )


class CaseCreated(StrictModel):
    case_id: UUID
    decision: ClinicalDecision


class ReviewRequest(StrictModel):
    disposition: ReviewDisposition
    rationale: str = Field(min_length=3, max_length=2000)
    amendments: Dict[str, Any] = Field(default_factory=dict)
    advice_plan: Optional[ReviewedAdvicePlan] = None
    follow_up_owner: Optional[str] = None
    follow_up_due_at: Optional[datetime] = None
