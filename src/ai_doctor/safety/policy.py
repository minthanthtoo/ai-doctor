"""Deterministic authorization checks for clinical capabilities.

This module is deliberately independent of language-model output.  A missing,
unknown, or malformed policy input is denied rather than inferred.
"""

from __future__ import annotations

from typing import List, Optional

from ai_doctor.domain.models import (
    CapabilityName,
    PatientSnapshot,
    SafetyDecision,
    SafetyStatus,
    UrgencyLevel,
    UserRole,
)
from ai_doctor.safety.registry import CapabilityPolicy, CapabilityRegistry


class SafetyGate:
    """Evaluates a single requested capability against its released envelope."""

    def __init__(self, registry: Optional[CapabilityRegistry] = None):
        self._registry = registry or CapabilityRegistry.default()

    @property
    def registry(self) -> CapabilityRegistry:
        return self._registry

    def evaluate(
        self,
        capability: CapabilityName,
        snapshot: PatientSnapshot,
        user_role: UserRole,
        requested_output: str,
        requested_action: Optional[str] = None,
        emergency_priority: UrgencyLevel = UrgencyLevel.INSUFFICIENT_DATA,
    ) -> SafetyDecision:
        """Return the only permitted next state; never raise an allow on uncertainty."""
        policy = self._registry.get(capability)
        if policy is None:
            return self._block("No released policy exists for requested capability.")

        blocks = self._base_blocks(policy, snapshot, user_role, requested_output, requested_action)
        if blocks:
            return SafetyDecision(
                status=SafetyStatus.BLOCK,
                reasons=["Requested capability is outside its released safety envelope."],
                hard_blocks=blocks,
                required_actions=[
                    "Use an authorized clinical workflow or request an in-scope capability."
                ],
            )

        if emergency_priority == UrgencyLevel.EMERGENCY_NOW:
            if capability == CapabilityName.EMERGENCY_TRIAGE:
                return SafetyDecision(
                    status=SafetyStatus.ESCALATE,
                    reasons=["Emergency-priority presentation requires immediate escalation."],
                    required_actions=[
                        "Display emergency instruction.",
                        "Seek emergency services now.",
                    ],
                )
            return SafetyDecision(
                status=SafetyStatus.ESCALATE,
                reasons=[
                    "Non-triage capability is suspended while emergency escalation is required."
                ],
                hard_blocks=[
                    "Emergency priority prevents diagnosis, prescribing, and routine advice workflows."
                ],
                required_actions=["Run emergency triage and seek emergency services now."],
            )

        required_actions: List[str] = []
        if policy.required_clinician_review:
            required_actions.append(
                "Clinician review is required before any clinical use or communication."
            )
        return SafetyDecision(
            status=SafetyStatus.ALLOW_REVIEW,
            reasons=["Requested capability is within its released safety envelope."],
            required_actions=required_actions,
        )

    @staticmethod
    def _block(reason: str) -> SafetyDecision:
        return SafetyDecision(
            status=SafetyStatus.BLOCK,
            reasons=["Requested capability is blocked by the safety gate."],
            hard_blocks=[reason],
            required_actions=["Do not generate or execute the requested output."],
        )

    @staticmethod
    def _base_blocks(
        policy: CapabilityPolicy,
        snapshot: PatientSnapshot,
        user_role: UserRole,
        requested_output: str,
        requested_action: Optional[str],
    ) -> List[str]:
        blocks: List[str] = []
        if policy.status != "enabled":
            blocks.append("Capability status is " + policy.status + ".")
        if user_role not in policy.allowed_roles:
            blocks.append("User role is not authorized for this capability.")
        if snapshot.age_years is None:
            if policy.age_required:
                blocks.append("Patient age is required for this capability.")
        elif not policy.minimum_age_years <= snapshot.age_years <= policy.maximum_age_years:
            blocks.append("Patient age is outside the authorized population.")
        if snapshot.pregnancy_status not in policy.allowed_pregnancy_statuses:
            blocks.append("Pregnancy status is outside the authorized population.")
        if requested_output in policy.prohibited_outputs:
            blocks.append("Requested output is explicitly prohibited.")
        elif requested_output not in policy.allowed_outputs:
            blocks.append("Requested output is not explicitly authorized.")
        if requested_action is not None:
            if requested_action in policy.prohibited_actions:
                blocks.append("Requested action is explicitly prohibited.")
            elif requested_action not in policy.allowed_actions:
                blocks.append("Requested action is not explicitly authorized.")
        return blocks
