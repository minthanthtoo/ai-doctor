"""Versioned, fail-closed capability policy registry."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_doctor.domain.models import CapabilityName, PregnancyStatus, UserRole


class CapabilityPolicy(BaseModel):
    """The complete authorization envelope for one clinical capability."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: CapabilityName
    status: str
    release_version: str = Field(min_length=1)
    knowledge_sha256: Optional[str] = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    age_required: bool = True
    allowed_roles: List[UserRole] = Field(min_length=1)
    minimum_age_years: float = Field(ge=0, le=130)
    maximum_age_years: float = Field(ge=0, le=130)
    allowed_pregnancy_statuses: List[PregnancyStatus] = Field(min_length=1)
    required_clinician_review: bool
    allowed_outputs: List[str] = Field(min_length=1)
    allowed_actions: List[str] = Field(default_factory=list)
    prohibited_outputs: List[str] = Field(default_factory=list)
    prohibited_actions: List[str] = Field(default_factory=list)

    @field_validator("status")
    @classmethod
    def status_is_known(cls, value: str) -> str:
        if value not in {"enabled", "disabled", "withdrawn", "pilot"}:
            raise ValueError("status must be enabled, disabled, withdrawn, or pilot")
        return value

    @model_validator(mode="after")
    def policy_is_unambiguous(self) -> "CapabilityPolicy":
        if self.minimum_age_years > self.maximum_age_years:
            raise ValueError("minimum_age_years cannot exceed maximum_age_years")
        overlap = set(self.allowed_outputs).intersection(self.prohibited_outputs)
        if overlap:
            raise ValueError(
                "an output cannot be both allowed and prohibited: " + ", ".join(sorted(overlap))
            )
        overlap = set(self.allowed_actions).intersection(self.prohibited_actions)
        if overlap:
            raise ValueError(
                "an action cannot be both allowed and prohibited: " + ", ".join(sorted(overlap))
            )
        return self


class RegistryDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    registry_version: str = Field(min_length=1)
    capabilities: List[CapabilityPolicy] = Field(min_length=1)

    @model_validator(mode="after")
    def capability_names_are_unique(self) -> "RegistryDocument":
        names = [policy.name for policy in self.capabilities]
        if len(names) != len(set(names)):
            raise ValueError("capability names must be unique")
        return self


class CapabilityRegistry:
    """Loads a static policy document and never guesses for missing policies."""

    def __init__(self, document: RegistryDocument):
        self._document = document
        self._policies: Dict[CapabilityName, CapabilityPolicy] = {
            policy.name: policy for policy in document.capabilities
        }

    @property
    def registry_version(self) -> str:
        return self._document.registry_version

    @classmethod
    def from_file(cls, path: Path) -> "CapabilityRegistry":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("capability registry could not be loaded") from exc
        registry = cls(RegistryDocument.model_validate(payload))
        registry._validate_executed_knowledge_releases()
        return registry

    @classmethod
    def default(cls) -> "CapabilityRegistry":
        path = Path(__file__).resolve().parent.parent / "config" / "capability_registry.json"
        return cls.from_file(path)

    def get(self, capability: CapabilityName) -> Optional[CapabilityPolicy]:
        return self._policies.get(capability)

    def require(self, capability: CapabilityName) -> CapabilityPolicy:
        policy = self.get(capability)
        if policy is None:
            raise KeyError("no policy is registered for capability " + capability.value)
        return policy

    def release_versions(self, capabilities: Iterable[CapabilityName]) -> Dict[str, str]:
        return {
            capability.value: self.require(capability).release_version
            for capability in capabilities
        }

    def knowledge_provenance(self, capability: CapabilityName) -> Dict[str, str]:
        """Return the pinned executable-rule provenance, when a capability has it."""
        policy = self.require(capability)
        if policy.knowledge_sha256 is None:
            return {}
        return {
            "release_version": policy.release_version,
            "sha256": policy.knowledge_sha256,
        }

    def provenance_for(self, capabilities: Iterable[CapabilityName]) -> Dict[str, Dict[str, str]]:
        """Return immutable release identifiers for a clinical decision record."""

        result: Dict[str, Dict[str, str]] = {}
        for capability in capabilities:
            policy = self.require(capability)
            provenance = {"release_version": policy.release_version}
            if policy.knowledge_sha256 is not None:
                provenance["sha256"] = policy.knowledge_sha256
            result[capability.value] = provenance
        return result

    def _validate_executed_knowledge_releases(self) -> None:
        """Fail startup if a policy differs from the locally executed rule release."""
        knowledge_dir = Path(__file__).resolve().parent.parent / "knowledge"
        artifacts = {
            CapabilityName.EMERGENCY_TRIAGE: knowledge_dir / "triage_rules.json",
            CapabilityName.DIAGNOSIS_SUPPORT: knowledge_dir / "diagnosis_rules.json",
        }
        for capability, artifact in artifacts.items():
            policy = self.require(capability)
            if policy.knowledge_sha256 is None:
                raise ValueError("knowledge digest is required for " + capability.value)
            try:
                content = artifact.read_bytes()
                artifact_release = json.loads(content.decode("utf-8"))["release"]
            except (OSError, UnicodeDecodeError, KeyError, json.JSONDecodeError) as exc:
                raise ValueError("executed knowledge artifact could not be loaded") from exc
            if artifact_release != policy.release_version:
                raise ValueError(
                    "registry release does not match executed knowledge for " + capability.value
                )
            if hashlib.sha256(content).hexdigest() != policy.knowledge_sha256:
                raise ValueError(
                    "registry knowledge digest does not match executed artifact for "
                    + capability.value
                )
