"""Governed Diagnostic Authority (GDA) core for HOARE.

Design/provenance record: 2026-09-12.

GDA lets an agent observe failures, diagnose them, propose bounded recovery,
and request admission for recovery actions. It never grants itself action
authority, creates trusted evidence, changes policy, or bypasses AEGIS.

Core contract:
DiagnosticObservation -> Diagnosis -> RecoveryPlan -> DiagnosticAdmission
-> RecoveryResult -> EvidenceAssessment
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import monotonic
from typing import FrozenSet, Mapping, Sequence


class DiagnosticAction(str, Enum):
    IMAGE_CROP = "IMAGE_CROP"
    IMAGE_RESIZE = "IMAGE_RESIZE"
    IMAGE_ENHANCE = "IMAGE_ENHANCE"
    IMAGE_ROTATE = "IMAGE_ROTATE"
    BARCODE_SCAN = "BARCODE_SCAN"
    OCR = "OCR"
    VISION_RETRY = "VISION_RETRY"
    REQUEST_RECAPTURE = "REQUEST_RECAPTURE"


class DiagnosticDecision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    ESCALATE = "ESCALATE"


@dataclass(frozen=True)
class DiagnosticObservation:
    session_id: str
    source_frame_id: str
    failure_code: str
    confidence: float
    facts: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Diagnosis:
    failure_code: str
    confidence: float
    rationale: str


@dataclass(frozen=True)
class DiagnosticLease:
    lease_id: str
    allowed_actions: FrozenSet[DiagnosticAction]
    max_attempts: int = 3
    max_duration_seconds: float = 30.0
    max_recovery_depth: int = 3
    max_compute_budget: float = 2.0

    def permits(self, action: DiagnosticAction) -> bool:
        return action in self.allowed_actions


@dataclass(frozen=True)
class RecoveryStep:
    action: DiagnosticAction
    parameters: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RecoveryPlan:
    diagnosis: Diagnosis
    steps: tuple[RecoveryStep, ...]
    rationale: str


@dataclass(frozen=True)
class DiagnosticAdmission:
    decision: DiagnosticDecision
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class RecoveryResult:
    success: bool
    attempts: int
    facts: Mapping[str, object] = field(default_factory=dict)
    error: str | None = None


@dataclass(frozen=True)
class EvidenceAssessment:
    verified: bool
    facts: Mapping[str, object] = field(default_factory=dict)
    reason: str | None = None


class DiagnosticLeaseController:
    """Enforces bounded diagnostic authority without granting action authority."""

    def __init__(self, lease: DiagnosticLease, *, started_at: float | None = None):
        self.lease = lease
        self.started_at = monotonic() if started_at is None else started_at
        self.attempts = 0
        self.depth = 0
        self.compute_used = 0.0

    def admit(self, plan: RecoveryPlan, *, compute_cost: float = 0.0) -> DiagnosticAdmission:
        if not plan.steps:
            return DiagnosticAdmission(DiagnosticDecision.DENY, ("empty_recovery_plan",))
        if self.attempts >= self.lease.max_attempts:
            return DiagnosticAdmission(DiagnosticDecision.ESCALATE, ("diagnostic_attempt_limit_reached",))
        if self.depth >= self.lease.max_recovery_depth:
            return DiagnosticAdmission(DiagnosticDecision.ESCALATE, ("diagnostic_depth_limit_reached",))
        if monotonic() - self.started_at > self.lease.max_duration_seconds:
            return DiagnosticAdmission(DiagnosticDecision.ESCALATE, ("diagnostic_lease_expired",))
        if compute_cost < 0 or self.compute_used + compute_cost > self.lease.max_compute_budget:
            return DiagnosticAdmission(DiagnosticDecision.ESCALATE, ("diagnostic_compute_budget_exceeded",))

        for step in plan.steps:
            if not self.lease.permits(step.action):
                return DiagnosticAdmission(
                    DiagnosticDecision.DENY,
                    (f"diagnostic_action_not_permitted:{step.action.value}",),
                )

        self.attempts += 1
        self.depth += 1
        self.compute_used += compute_cost
        return DiagnosticAdmission(DiagnosticDecision.ALLOW, ("bounded_diagnostic_recovery",))

    def reset_depth(self) -> None:
        self.depth = 0


def diagnose(observation: DiagnosticObservation) -> Diagnosis:
    """Convert an observation into a deterministic diagnosis record.

    The LLM/agent may propose richer reasoning outside this function, but the
    resulting diagnosis remains an explicit object before recovery admission.
    """
    rationale = str(observation.facts.get("rationale") or observation.failure_code)
    return Diagnosis(
        failure_code=observation.failure_code,
        confidence=max(0.0, min(1.0, observation.confidence)),
        rationale=rationale,
    )


def build_recovery_plan(
    diagnosis: Diagnosis,
    steps: Sequence[RecoveryStep],
    *,
    rationale: str,
) -> RecoveryPlan:
    """Build a proposed plan; admission is deliberately a separate operation."""
    return RecoveryPlan(
        diagnosis=diagnosis,
        steps=tuple(steps),
        rationale=rationale,
    )


def assess_evidence(*, verified: bool, facts: Mapping[str, object] | None = None, reason: str | None = None) -> EvidenceAssessment:
    """Record evidence assessment; this function does not manufacture identity."""
    return EvidenceAssessment(verified=bool(verified), facts=dict(facts or {}), reason=reason)


__all__ = [
    "DiagnosticAction",
    "DiagnosticDecision",
    "DiagnosticObservation",
    "Diagnosis",
    "DiagnosticLease",
    "RecoveryStep",
    "RecoveryPlan",
    "DiagnosticAdmission",
    "RecoveryResult",
    "EvidenceAssessment",
    "DiagnosticLeaseController",
    "diagnose",
    "build_recovery_plan",
    "assess_evidence",
]
