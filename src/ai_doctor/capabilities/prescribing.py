"""Protocol-bounded prescription drafting.

This module deliberately produces a *draft*, never an order.  Protocol content is
data supplied by the deploying clinical governance process; no clinical rule is
created here.
"""

from __future__ import annotations

import base64
import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ai_doctor.domain.models import (
    PatientSnapshot,
    PrescriptionDraft,
    PrescriptionItem,
    RuleTrace,
    UserRole,
    utc_now,
)

APPROVING_ROLES = frozenset({UserRole.PHYSICIAN, UserRole.PHARMACIST})
_DEFAULT_PROTOCOL_PATH = Path(__file__).parents[1] / "knowledge" / "prescribing_protocols.json"


class ProtocolValidationError(ValueError):
    """A purported protocol is not an approved, signed protocol record."""


def canonical_protocol_bytes(record: Mapping[str, Any]) -> bytes:
    """Canonical signed bytes, excluding the detached signature value itself."""

    payload = copy.deepcopy(dict(record))
    approval = payload.get("approval")
    if isinstance(approval, dict):
        approval.pop("signature", None)
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


@dataclass(frozen=True)
class Ed25519ProtocolVerifier:
    """Verify detached Ed25519 signatures against a release-controlled key ring."""

    public_keys_base64: Mapping[str, str]

    def __call__(self, record: Mapping[str, Any]) -> bool:
        approval = record.get("approval")
        if not isinstance(approval, Mapping):
            return False
        key_id = approval.get("key_id")
        signature_text = approval.get("signature")
        if not isinstance(key_id, str) or not isinstance(signature_text, str):
            return False
        public_key_text = self.public_keys_base64.get(key_id)
        if public_key_text is None:
            return False
        try:
            public_key = Ed25519PublicKey.from_public_bytes(
                base64.b64decode(public_key_text, validate=True)
            )
            signature = base64.b64decode(signature_text, validate=True)
            public_key.verify(signature, canonical_protocol_bytes(record))
            return True
        except (ValueError, InvalidSignature):
            return False


@dataclass(frozen=True)
class ProtocolRepository:
    """Read-only repository for release-controlled protocol records.

    ``signature_verifier`` must be supplied by production deployment and verifies
    the detached signature against the complete protocol record.  The default only
    admits records explicitly marked as an approved fixture, which is useful for
    local test environments and does not make an unsigned record executable.
    """

    records: Mapping[str, Mapping[str, Any]]
    signature_verifier: Optional[Callable[[Mapping[str, Any]], bool]] = None
    allow_test_fixtures: bool = False

    @classmethod
    def from_file(
        cls,
        path: Path = _DEFAULT_PROTOCOL_PATH,
        signature_verifier: Optional[Callable[[Mapping[str, Any]], bool]] = None,
        allow_test_fixtures: bool = False,
    ) -> "ProtocolRepository":
        with Path(path).open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        protocols = payload.get("protocols", [])
        if not isinstance(protocols, list):
            raise ProtocolValidationError("protocols must be a list")
        records: Dict[str, Mapping[str, Any]] = {}
        for protocol in protocols:
            if not isinstance(protocol, dict) or not isinstance(protocol.get("id"), str):
                raise ProtocolValidationError("each protocol requires a string id")
            if protocol["id"] in records:
                raise ProtocolValidationError("duplicate protocol id")
            records[protocol["id"]] = protocol
        return cls(
            records=records,
            signature_verifier=signature_verifier,
            allow_test_fixtures=allow_test_fixtures,
        )

    def approved(self, protocol_id: str) -> Mapping[str, Any]:
        record = self.records.get(protocol_id)
        if record is None:
            raise ProtocolValidationError("no approved protocol matches the request")
        approval = record.get("approval")
        if not isinstance(approval, Mapping) or approval.get("state") != "approved":
            raise ProtocolValidationError("protocol is not approved")
        if not approval.get("signer_id") or not approval.get("signature"):
            raise ProtocolValidationError("protocol has no signed approval")
        if self.signature_verifier is None:
            if not self.allow_test_fixtures:
                raise ProtocolValidationError("no protocol signature verifier configured")
            if approval.get("signature") != "LOCAL_TEST_FIXTURE_ONLY":
                raise ProtocolValidationError("invalid local test-fixture signature")
        elif not self.signature_verifier(record):
            raise ProtocolValidationError("protocol signature verification failed")
        _validate_protocol_shape(record)
        return record


def _validate_protocol_shape(protocol: Mapping[str, Any]) -> None:
    required = ("id", "version", "medication", "required_inputs", "contraindications")
    if any(name not in protocol for name in required):
        raise ProtocolValidationError("approved protocol is missing required fields")
    if not protocol["id"] or not protocol["version"]:
        raise ProtocolValidationError("approved protocol is missing an id or version")
    medication = protocol["medication"]
    if not isinstance(medication, Mapping):
        raise ProtocolValidationError("protocol medication must be an object")
    for name in ("name", "dose", "route", "frequency", "indication"):
        if not medication.get(name):
            raise ProtocolValidationError("protocol medication is incomplete")
    if not isinstance(protocol["required_inputs"], list):
        raise ProtocolValidationError("required_inputs must be a list")
    if not any(
        str(requirement).startswith("condition:") for requirement in protocol["required_inputs"]
    ):
        raise ProtocolValidationError(
            "protocol requires at least one clinician-verified indication condition"
        )
    if not isinstance(protocol["contraindications"], list):
        raise ProtocolValidationError("contraindications must be a list")


def build_prescription_draft(
    snapshot: PatientSnapshot,
    protocol_id: str,
    repository: Optional[ProtocolRepository] = None,
) -> PrescriptionDraft:
    """Build a non-executable clinician-review draft from one approved protocol.

    Any missing required input, unknown allergy state, possible pregnancy, or
    contraindication blocks the entire draft.  Callers must use a clinician review
    transition before presenting the draft as approved.
    """

    repository = repository or ProtocolRepository.from_file()
    try:
        protocol = repository.approved(protocol_id)
    except ProtocolValidationError as exc:
        return _blocked_draft(str(exc), protocol_id)

    missing = _missing_inputs(snapshot, protocol["required_inputs"])
    blocks = _hard_blocks(snapshot, protocol)
    trace = _trace(protocol, missing, blocks)
    if missing or blocks:
        return PrescriptionDraft(
            status="blocked",
            hard_blocks=blocks,
            missing_inputs=missing,
            protocol_trace=[trace],
            clinician_approval_required=True,
            executable=False,
        )

    medication = protocol["medication"]
    item = PrescriptionItem(
        medication_name=str(medication["name"]),
        dose=str(medication["dose"]),
        route=str(medication["route"]),
        frequency=str(medication["frequency"]),
        duration=_optional_string(medication.get("duration")),
        indication=str(medication["indication"]),
        protocol_id=str(protocol["id"]),
        protocol_version=str(protocol["version"]),
        monitoring=_strings(medication.get("monitoring", [])),
        warnings=_strings(medication.get("warnings", [])),
    )
    return PrescriptionDraft(items=[item], protocol_trace=[trace], executable=False)


def approve_prescription_draft(
    draft: PrescriptionDraft, clinician_id: str, role: UserRole
) -> PrescriptionDraft:
    """Record a clinician approval without granting EHR/order execution authority."""

    if role not in APPROVING_ROLES:
        raise PermissionError("only a physician or pharmacist may approve a prescription draft")
    if draft.status != "pending_clinician_review" or not draft.items:
        raise ValueError("only an unblocked, populated draft may be approved")
    if draft.hard_blocks or draft.missing_inputs:
        raise ValueError("a draft with unresolved safety conditions cannot be approved")
    return draft.model_copy(
        update={
            "status": "clinician_approved_draft",
            "approved_by": clinician_id,
            "approved_at": utc_now(),
            "clinician_approval_required": True,
            "executable": False,
        }
    )


def _blocked_draft(reason: str, protocol_id: str) -> PrescriptionDraft:
    return PrescriptionDraft(
        status="blocked",
        hard_blocks=[reason],
        protocol_trace=[
            RuleTrace(rule_id=protocol_id, rule_version="unavailable", result="BLOCKED")
        ],
        clinician_approval_required=True,
        executable=False,
    )


def _missing_inputs(snapshot: PatientSnapshot, required_inputs: Sequence[Any]) -> List[str]:
    missing: List[str] = []

    # These are platform-wide drafting invariants. A protocol cannot weaken them
    # by omitting a field from its own signed required-input list.
    if snapshot.age_years is None:
        missing.append("age_years")
    if not snapshot.confirmed_by_clinician:
        missing.append("confirmed_by_clinician")
    if not snapshot.allergy_status_confirmed:
        missing.append("allergy_status_confirmed")
    if not snapshot.medication_list_confirmed:
        missing.append("medication_list_confirmed")
    if snapshot.pregnancy_status.value == "unknown":
        missing.append("pregnancy_status")

    for requirement in required_inputs:
        key = str(requirement)
        if (
            key == "age_years"
            and snapshot.age_years is None
            or key == "confirmed_by_clinician"
            and not snapshot.confirmed_by_clinician
            or key == "allergy_status_confirmed"
            and not snapshot.allergy_status_confirmed
            or key == "medication_list_confirmed"
            and not snapshot.medication_list_confirmed
            or key == "pregnancy_status"
            and snapshot.pregnancy_status.value == "unknown"
            or key.startswith("condition:")
            and not _has_condition(
                snapshot, key.split(":", 1)[1], require_clinician_verification=True
            )
            or key.startswith("lab:")
            and not _has_lab(snapshot, key.split(":", 1)[1])
        ):
            missing.append(key)
        elif key not in {
            "age_years",
            "allergy_status_confirmed",
            "medication_list_confirmed",
            "pregnancy_status",
            "confirmed_by_clinician",
        } and not key.startswith(("condition:", "lab:")):
            # Unknown requirements cannot be silently assumed satisfied.
            missing.append(key)
    return list(dict.fromkeys(missing))


def _hard_blocks(snapshot: PatientSnapshot, protocol: Mapping[str, Any]) -> List[str]:
    blocks: List[str] = []
    medication = protocol["medication"]
    allergy_names = {str(medication["name"]).casefold()}
    allergy_names.update(
        value.casefold() for value in _strings(medication.get("allergy_aliases", []))
    )
    matched_allergies = [
        a.substance for a in snapshot.allergies if a.substance.casefold() in allergy_names
    ]
    if matched_allergies:
        blocks.append("documented allergy to protocol medication: " + ", ".join(matched_allergies))
    if protocol.get("pregnancy_check_required", True) and snapshot.pregnancy_status.value not in {
        "not_pregnant",
        "not_applicable",
    }:
        blocks.append("pregnancy status does not permit this protocol")
    for contraindication in protocol["contraindications"]:
        if _has_condition(snapshot, str(contraindication)):
            blocks.append("protocol contraindication present: " + str(contraindication))
    contraindicated_medications = {
        value.casefold() for value in _strings(protocol.get("contraindicated_medications", []))
    }
    for current in snapshot.medications:
        current_names = {current.name.casefold()}
        if current.normalized_id:
            current_names.add(current.normalized_id.casefold())
        if current_names.intersection(contraindicated_medications):
            blocks.append("protocol-listed interacting medication present: " + current.name)
    population = protocol.get("population", {})
    if isinstance(population, Mapping) and snapshot.age_years is not None:
        minimum = population.get("minimum_age_years")
        maximum = population.get("maximum_age_years")
        if minimum is not None and snapshot.age_years < float(minimum):
            blocks.append("patient age is below the protocol population")
        if maximum is not None and snapshot.age_years > float(maximum):
            blocks.append("patient age is above the protocol population")
    return blocks


def _trace(protocol: Mapping[str, Any], missing: List[str], blocks: List[str]) -> RuleTrace:
    result = "BLOCKED" if missing or blocks else "EVALUATED_NO_FINDING"
    return RuleTrace(
        rule_id=str(protocol["id"]),
        rule_version=str(protocol["version"]),
        result=result,
        missing_inputs=missing,
        trigger_fact_refs=blocks,
    )


def _has_condition(
    snapshot: PatientSnapshot,
    expected: str,
    require_clinician_verification: bool = False,
) -> bool:
    for item in snapshot.conditions:
        if item.name.casefold() != expected.casefold() or item.status != "active":
            continue
        if (
            require_clinician_verification
            and item.verification_status.value != "clinician_verified"
        ):
            continue
        return True
    return False


def _has_lab(snapshot: PatientSnapshot, code: str) -> bool:
    return any(item.code.casefold() == code.casefold() for item in snapshot.labs)


def _strings(value: Any) -> List[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _optional_string(value: Any) -> Optional[str]:
    return str(value) if value is not None else None
