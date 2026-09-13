"""Governed remediation coordinator for the HOARE control loop.

Provenance: 2026-09-13.

This coordinator connects the already-separated remediation stages:
proposal -> fresh admission -> fresh signed execution preparation.
It never executes, never manufactures ALLOW, and never inherits prior
execution authorization.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from hoare_pick_admission import PickAdmission, PickRequest, ResourceRoute
from hoare_remediation_admission import (
    RemediationAdmissionCandidate,
    admit_remediation_candidate,
)
from hoare_remediation_execution import (
    RemediationExecutionAuthorization,
    prepare_remediation_execution,
)
from product_verification import ProductIdentity


SCHEMA_VERSION = "hoare.remediation-coordinator.v1"
COORDINATOR_VERSION = "1.0.0"


class RemediationCoordinatorError(ValueError):
    """Raised when governed remediation cannot progress to execution preparation."""


@dataclass(frozen=True)
class RemediationExecutionPreparation:
    """Fresh admission plus fresh signed execution preparation."""

    admission: PickAdmission
    execution: RemediationExecutionAuthorization

    @property
    def allowed(self) -> bool:
        return self.execution.allowed


def coordinate_remediation(
    *,
    candidate: RemediationAdmissionCandidate,
    identity: ProductIdentity,
    source_frame_id: str,
    evidence_signature: str,
    capability_version: str,
    contract_version: str,
    request_id: str,
    secret: str,
    resource_route: ResourceRoute | None = None,
    quantity: int = 1,
    now: float | None = None,
    ttl_seconds: float = 30.0,
) -> RemediationExecutionPreparation:
    """Run the governed remediation stages up to, but not including, execution.

    The coordinator deliberately performs no executor call. It obtains a fresh
    admission from the existing ``admit_pick`` authority and only then creates
    a new signed request and independent authorization.
    """
    if candidate.authority != "admission-required":
        raise RemediationCoordinatorError("candidate_authority_invalid")
    if candidate.can_execute:
        raise RemediationCoordinatorError("candidate_must_not_be_executable")

    admission = admit_remediation_candidate(
        candidate=candidate,
        identity=identity,
        resource_route=resource_route,
    )

    execution = prepare_remediation_execution(
        candidate=candidate,
        admission=admission,
        source_frame_id=source_frame_id,
        evidence_signature=evidence_signature,
        quantity=quantity,
        capability_version=capability_version,
        contract_version=contract_version,
        request_id=request_id,
        secret=secret,
        now=now,
        ttl_seconds=ttl_seconds,
    )

    return RemediationExecutionPreparation(
        admission=admission,
        execution=execution,
    )


__all__ = [
    "COORDINATOR_VERSION",
    "RemediationCoordinatorError",
    "RemediationExecutionPreparation",
    "SCHEMA_VERSION",
    "coordinate_remediation",
]
