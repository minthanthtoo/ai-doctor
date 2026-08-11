from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from ai_doctor.domain.models import StrictModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FactKind(str, Enum):
    SYMPTOM = "symptom"
    VITAL = "vital"
    MEDICATION = "medication"
    ALLERGY = "allergy"
    CONDITION = "condition"
    DOCUMENT_CLAIM = "document_claim"
    USER_NOTE = "user_note"


class LongitudinalVerification(str, Enum):
    USER_REPORTED = "user_reported"
    DEVICE_OBSERVED = "device_observed"
    DOCUMENT_EXTRACTED_CANDIDATE = "document_extracted_candidate"
    USER_CONFIRMED = "user_confirmed"
    CONFLICTED = "conflicted"
    SUPERSEDED = "superseded"
    RETRACTED = "retracted"


class EpisodeState(str, Enum):
    INTAKE = "intake"
    INCOMPLETE = "incomplete"
    COLLECTING_WORKUP = "collecting_workup"
    SAFETY_REASSESSMENT = "safety_reassessment"
    EMERGENCY_LOCK = "emergency_lock"
    URGENT_ROUTE = "urgent_route"
    POSSIBILITY_DRAFT = "possibility_draft"
    EVIDENCE_CHECK = "evidence_check"
    CRITIQUE = "critique"
    POSSIBILITY_MAP = "possibility_map"
    MONITORING = "monitoring"
    USER_REPORTED_IMPROVED = "user_reported_improved"
    EXPIRED = "expired"
    CLOSED_BY_USER = "closed_by_user"


class CoverageState(str, Enum):
    EVALUATED = "evaluated"
    NOT_ASSESSED_MISSING_INPUT = "not_assessed_missing_input"
    NOT_ASSESSED_QUALITY_FAILURE = "not_assessed_quality_failure"
    STALE = "stale"
    CONFLICTED = "conflicted"
    OUT_OF_SCOPE = "out_of_scope"
    RELEASE_UNAVAILABLE = "release_unavailable"


class ObservationKind(str, Enum):
    HEART_RATE = "heart_rate"
    BLOOD_PRESSURE = "blood_pressure"
    OXYGEN_SATURATION = "oxygen_saturation"
    TEMPERATURE = "temperature"
    GLUCOSE = "glucose"
    WEIGHT = "weight"
    RESPIRATORY_RATE = "respiratory_rate"
    SYMPTOM_SCORE = "symptom_score"


class ObservationQuality(str, Enum):
    ACCEPTED = "accepted"
    IMPLAUSIBLE = "implausible"
    INCOMPLETE = "incomplete"
    STALE = "stale"
    DUPLICATE = "duplicate"


class ClinicalFactRevision(StrictModel):
    fact_id: UUID = Field(default_factory=uuid4)
    revision_id: UUID = Field(default_factory=uuid4)
    profile_id: UUID
    kind: FactKind
    code_system: Optional[str] = Field(default=None, max_length=120)
    code: Optional[str] = Field(default=None, max_length=160)
    display: str = Field(min_length=1, max_length=300)
    value: Dict[str, Any] = Field(default_factory=dict)
    unit: Optional[str] = Field(default=None, max_length=80)
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    recorded_at: datetime = Field(default_factory=utc_now)
    source_type: str = Field(pattern="^(manual|device|document|imported|system)$")
    source_object_id: Optional[UUID] = None
    verification: LongitudinalVerification = LongitudinalVerification.USER_REPORTED
    certainty: str = Field(default="asserted", pattern="^(asserted|denied|unknown)$")
    supersedes_revision_id: Optional[UUID] = None
    retracts_revision_id: Optional[UUID] = None
    conflict_group_id: Optional[UUID] = None
    created_by: str = Field(default="user", pattern="^(user|local_rule|local_model)$")

    @model_validator(mode="after")
    def validate_temporal_order(self) -> "ClinicalFactRevision":
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to cannot precede effective_from")
        if self.created_by == "local_model" and self.verification not in {
            LongitudinalVerification.DOCUMENT_EXTRACTED_CANDIDATE,
            LongitudinalVerification.USER_REPORTED,
        }:
            raise ValueError("a model cannot create a verified clinical fact")
        return self


class SourceArtifact(StrictModel):
    artifact_id: UUID = Field(default_factory=uuid4)
    profile_id: UUID
    kind: str = Field(pattern="^(photo|pdf|lab_report|discharge_note|prescription_image)$")
    encrypted_blob_ref: str = Field(min_length=1, max_length=500)
    content_hash: str = Field(pattern="^[a-f0-9]{64}$")
    captured_at: datetime = Field(default_factory=utc_now)
    extraction_status: str = Field(
        default="not_processed",
        pattern="^(not_processed|candidate_extracted|rejected|failed)$",
    )
    extracted_candidate_fact_ids: List[UUID] = Field(default_factory=list, max_length=200)
    user_confirmed_at: Optional[datetime] = None


class Observation(StrictModel):
    observation_id: UUID = Field(default_factory=uuid4)
    profile_id: UUID
    episode_id: Optional[UUID] = None
    kind: ObservationKind
    raw_value: Dict[str, float]
    raw_unit: str = Field(min_length=1, max_length=40)
    normalized_value: Dict[str, float] = Field(default_factory=dict)
    normalized_unit: Optional[str] = Field(default=None, max_length=40)
    measured_at: datetime
    entered_at: datetime = Field(default_factory=utc_now)
    entry_method: str = Field(default="manual", pattern="^(manual|csv|connected_device)$")
    device_metadata: Dict[str, str] = Field(default_factory=dict)
    quality: ObservationQuality = ObservationQuality.ACCEPTED
    source_fact_revision_ids: List[UUID] = Field(default_factory=list)


class LongitudinalSnapshot(StrictModel):
    snapshot_id: UUID = Field(default_factory=uuid4)
    profile_id: UUID
    episode_id: Optional[UUID] = None
    cutoff_at: datetime = Field(default_factory=utc_now)
    known_at: datetime = Field(default_factory=utc_now)
    fact_revision_ids: List[UUID] = Field(default_factory=list)
    observation_ids: List[UUID] = Field(default_factory=list)
    conflict_group_ids: List[UUID] = Field(default_factory=list)
    stale_fact_ids: List[UUID] = Field(default_factory=list)
    coverage: Dict[str, CoverageState] = Field(default_factory=dict)
    jurisdiction: str = "MM"
    preferred_language: str = Field(default="my", pattern="^(my|en)$")
    release_hashes: Dict[str, str] = Field(default_factory=dict)


class LongitudinalTriageAssessment(StrictModel):
    assessment_id: UUID = Field(default_factory=uuid4)
    episode_id: UUID
    snapshot_id: UUID
    urgency: str = Field(
        pattern="^(emergency_now|urgent_same_day|in_person_24_48h|self_care_possible|insufficient_data|out_of_scope)$"
    )
    finding_codes: List[str] = Field(default_factory=list)
    evaluated_rule_ids: List[str] = Field(default_factory=list)
    unavailable_rule_ids: List[str] = Field(default_factory=list)
    missing_inputs: List[str] = Field(default_factory=list)
    stale_inputs: List[str] = Field(default_factory=list)
    conflict_group_ids: List[UUID] = Field(default_factory=list)
    coverage: CoverageState
    emergency_lock: bool = False
    instruction_content_id: Optional[str] = None
    rule_release: str
    generated_at: datetime = Field(default_factory=utc_now)


class HypothesisCandidate(StrictModel):
    hypothesis_id: UUID = Field(default_factory=uuid4)
    terminology_id: str = Field(min_length=1, max_length=160)
    label_my: str = Field(min_length=1, max_length=300)
    label_en: str = Field(min_length=1, max_length=300)
    status: str = Field(pattern="^(active|less_supported|unresolved|not_assessable)$")
    dangerous_if_missed: bool = False
    support_fact_ids: List[UUID] = Field(default_factory=list, max_length=20)
    contradicting_fact_ids: List[UUID] = Field(default_factory=list, max_length=20)
    missing_question_ids: List[str] = Field(default_factory=list, max_length=20)
    evidence_ids: List[str] = Field(default_factory=list, max_length=20)
    source_release: str
    never_confirmed_as_diagnosis: bool = True

    @model_validator(mode="after")
    def enforce_candidate_only(self) -> "HypothesisCandidate":
        if not self.never_confirmed_as_diagnosis:
            raise ValueError("patient-facing hypotheses can never be confirmed diagnoses")
        return self


class Episode(StrictModel):
    episode_id: UUID = Field(default_factory=uuid4)
    profile_id: UUID
    chief_concern: str = Field(min_length=1, max_length=1000)
    state: EpisodeState = EpisodeState.INTAKE
    scope_pack: str = "cardiometabolic-v0-preclinical"
    linked_fact_revision_ids: List[UUID] = Field(default_factory=list)
    latest_snapshot_id: Optional[UUID] = None
    latest_assessment_id: Optional[UUID] = None
    unsupported_reason_codes: List[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=utc_now)
    last_assessed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None


class Workup(StrictModel):
    workup_id: UUID = Field(default_factory=uuid4)
    episode_id: UUID
    state: EpisodeState
    approved_question_ids: List[str] = Field(default_factory=list, max_length=50)
    answered_question_ids: List[str] = Field(default_factory=list, max_length=50)
    deferred_question_ids: List[str] = Field(default_factory=list, max_length=50)
    hypothesis_candidates: List[HypothesisCandidate] = Field(default_factory=list, max_length=8)
    reasoning_rounds_used: int = Field(default=0, ge=0, le=2)
    model_calls_used: int = Field(default=0, ge=0, le=3)
    retrieval_calls_used: int = Field(default=0, ge=0, le=4)
    transition_reason_code: str = Field(default="created", max_length=160)
    snapshot_id: UUID
    snapshot_hash: str = Field(pattern="^[a-f0-9]{64}$")
    last_transition_at: datetime = Field(default_factory=utc_now)
    expires_at: Optional[datetime] = None


class MonitoringTask(StrictModel):
    task_id: UUID = Field(default_factory=uuid4)
    profile_id: UUID
    episode_id: Optional[UUID] = None
    task_type: str = Field(
        pattern="^(record_vital|symptom_checkin|reconfirm_medication|read_education|contact_service)$"
    )
    content_id: Optional[str] = None
    origin: str = Field(default="patient_created", pattern="^(patient_created|signed_template|routing_rule)$")
    due_at: datetime
    expires_at: datetime
    reminder_policy_id: str
    completion_mode: str = Field(
        default="user_acknowledgement",
        pattern="^(user_acknowledgement|structured_response|external_contact_confirmed_by_user)$",
    )
    status: str = Field(
        default="scheduled",
        pattern="^(scheduled|due|completed|skipped|expired|cancelled)$",
    )
    disclaimer_key: str = "no_clinician_monitoring_v1"


class MonitoringPlan(StrictModel):
    plan_id: UUID = Field(default_factory=uuid4)
    profile_id: UUID
    episode_id: Optional[UUID] = None
    status: str = Field(default="active", pattern="^(active|paused|completed|expired)$")
    task_ids: List[UUID] = Field(default_factory=list)
    required_observation_kinds: List[ObservationKind] = Field(default_factory=list)
    alert_policy_id: str
    expires_at: datetime
    user_acknowledgment_required: bool = True


class LocalAlert(StrictModel):
    alert_id: UUID = Field(default_factory=uuid4)
    profile_id: UUID
    episode_id: Optional[UUID] = None
    trigger_rule_id: str
    level: str = Field(
        pattern="^(information|repeat_measurement|routine_contact|urgent_assessment|emergency_now)$"
    )
    instruction_content_id: str
    scheduled_at: datetime = Field(default_factory=utc_now)
    displayed_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    expired_at: Optional[datetime] = None
    delivery_state: str = Field(
        default="scheduled",
        pattern="^(scheduled|push_accepted|displayed|delivery_unknown|acknowledged|expired)$",
    )
    repeat_policy_id: str


class ConsentReceipt(StrictModel):
    consent_receipt_id: UUID = Field(default_factory=uuid4)
    purpose: str = Field(pattern="^(symptom_reasoning|document_extraction|evidence_synthesis)$")
    provider: str = Field(min_length=1, max_length=160)
    model: str = Field(min_length=1, max_length=200)
    disclosed_field_classes: List[str] = Field(min_length=1, max_length=30)
    snapshot_hash: str = Field(pattern="^[a-f0-9]{64}$")
    issued_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime
    revoked_at: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_consent(self) -> "ConsentReceipt":
        if self.expires_at <= self.issued_at:
            raise ValueError("consent expiry must follow issuance")
        return self


class MinimizedClinicalFact(StrictModel):
    fact_id: UUID
    terminology_id: str = Field(min_length=1, max_length=160)
    value_text: str = Field(min_length=1, max_length=240)
    verification: LongitudinalVerification


class EvidenceExcerpt(StrictModel):
    evidence_id: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=240)
    excerpt: str = Field(min_length=1, max_length=1200)
    release_id: str = Field(min_length=1, max_length=160)


class ModelRunRequest(StrictModel):
    run_id: UUID = Field(default_factory=uuid4)
    task: str = Field(pattern="^(possibility_generation|evidence_refinement|structured_synthesis)$")
    consent: ConsentReceipt
    snapshot_hash: str = Field(pattern="^[a-f0-9]{64}$")
    prompt_release: str
    schema_release: str
    evidence_release: str
    facts: List[MinimizedClinicalFact] = Field(min_length=1, max_length=100)
    evidence: List[EvidenceExcerpt] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def consent_matches_snapshot(self) -> "ModelRunRequest":
        if self.consent.snapshot_hash != self.snapshot_hash:
            raise ValueError("consent is not bound to this snapshot")
        if self.consent.revoked_at is not None:
            raise ValueError("consent has been revoked")
        if self.consent.expires_at <= utc_now():
            raise ValueError("consent has expired")
        return self


class CandidateContribution(StrictModel):
    run_id: UUID
    snapshot_hash: str = Field(pattern="^[a-f0-9]{64}$")
    hypotheses: List[HypothesisCandidate] = Field(default_factory=list, max_length=5)
    dangerous_alternatives: List[HypothesisCandidate] = Field(default_factory=list, max_length=3)
    proposed_question_ids: List[str] = Field(default_factory=list, max_length=20)
    abstention_reason: Optional[str] = Field(default=None, max_length=500)
    provider: str
    model: str
    model_release: str
    prompt_release: str
    schema_release: str
    validation_status: str = Field(pattern="^(accepted|rejected|disabled)$")


class EncryptedEnvelope(StrictModel):
    opaque_object_id: str = Field(min_length=16, max_length=200, pattern="^[A-Za-z0-9_-]+$")
    profile_pseudonym: str = Field(min_length=16, max_length=200, pattern="^[A-Za-z0-9_-]+$")
    device_id: str = Field(min_length=8, max_length=160, pattern="^[A-Za-z0-9_-]+$")
    client_sequence: int = Field(ge=1)
    ciphertext: str = Field(min_length=16, max_length=2_000_000)
    nonce: str = Field(min_length=12, max_length=200)
    aad_hash: str = Field(pattern="^[a-f0-9]{64}$")
    ciphertext_hash: str = Field(pattern="^[a-f0-9]{64}$")
    signature: str = Field(min_length=16, max_length=500)
    created_at: datetime = Field(default_factory=utc_now)
    ttl_seconds: int = Field(default=31_536_000, ge=3600, le=315_360_000)
    envelope_version: str = "1"


class SyncTombstone(StrictModel):
    tombstone_id: UUID = Field(default_factory=uuid4)
    profile_pseudonym: str = Field(min_length=16, max_length=200, pattern="^[A-Za-z0-9_-]+$")
    opaque_object_id: str = Field(min_length=16, max_length=200, pattern="^[A-Za-z0-9_-]+$")
    created_at: datetime = Field(default_factory=utc_now)


class PushSubscription(StrictModel):
    subscription_id: UUID = Field(default_factory=uuid4)
    profile_pseudonym: str = Field(min_length=16, max_length=200, pattern="^[A-Za-z0-9_-]+$")
    endpoint: str = Field(min_length=20, max_length=2000)
    p256dh: str = Field(min_length=16, max_length=500)
    auth: str = Field(min_length=8, max_length=500)
    created_at: datetime = Field(default_factory=utc_now)


class PushSchedule(StrictModel):
    opaque_schedule_id: str = Field(min_length=16, max_length=200, pattern="^[A-Za-z0-9_-]+$")
    profile_pseudonym: str = Field(min_length=16, max_length=200, pattern="^[A-Za-z0-9_-]+$")
    subscription_id: UUID
    due_at: datetime
    repeat_after_seconds: Optional[int] = Field(default=None, ge=60, le=604800)
    max_repeats: int = Field(default=0, ge=0, le=100)
    expires_at: datetime

    @model_validator(mode="after")
    def validate_schedule(self) -> "PushSchedule":
        if self.expires_at <= self.due_at:
            raise ValueError("schedule expiry must follow due time")
        if self.max_repeats and self.repeat_after_seconds is None:
            raise ValueError("repeat interval is required when repeats are enabled")
        return self
