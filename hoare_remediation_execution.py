"""Governed remediation execution orchestration for HOARE.

Provenance: 2026-09-13.

This module is the bridge between an already-admitted remediation candidate and
SHELF-SCOUTER's existing signed execution boundary. It deliberately stops at
independent execution authorization. The existing executor remains the only
component that performs the physical/domain operation.

Security invariant:
    proposal != candidate != admission != authorization != execution

The orchestration never manufactures ALLOW, never inherits prior authorization,
and never calls the executor directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from hoare_execution_plan import ExecutionPlan, compile_execution_plan
from hoare_execution_request import (
    ExecutionAuthorization,
    ExecutionRequest,
    authorize_execution,
    compile_execution_request,
    execution_signing_secret,
)
from hoare_pick_admission import AdmissionDecision, PickAdmission
from hoare_remediation_admission import RemediationAdmissionCandidate


SCHEMA_VERSION = "hoare.remediation-execution.v1"
ORCHESTRATOR_VERSION = "1.0.0"


class RemediationExecutionError(ValueError):
    """Raised when an admitted remediation cannot enter signed execution."""


@dataclass(frozen=True)
class RemediationExecutionBinding:
    """Immutable provenance carried alongside a fresh remediation execution."""

    schema: str
    orchestrator_version: str
    proposal_id: str
    proposal_hash: str
    candidate_hash: str
    original_execution_id: str | None
    action: str
    original_execution_boundary: Mapping[str, Any]
    new_admission_hash: str
    authority: str = "signed-execution-required"
    can_execute: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "orchestrator_version": self.orchestrator_version,
            "proposal_id": self.proposal_id,
            "proposal_hash": self.proposal_hash,
            "candidate_hash": self.candidate_hash,
            "original_execution_id": self.original_execution_id,
            "action": self.action,
            "original_execution_boundary": dict(self.original_execution_boundary),
            "new_admission_hash": self.new_admission_hash,
            "authority": self.authority,
            "can_execute": self.can_execute,
        }


@dataclass(frozen=True)
class RemediationExecutionAuthorization:
    """Fresh plan/request/authorization bundle for the existing executor."""

    binding: RemediationExecutionBinding
    plan: ExecutionPlan
    request: ExecutionRequest
    authorization: ExecutionAuthorization

    @property
    def allowed(self) -> bool:
        return self.authorization.allowed



def _admission_hash(admission: PickAdmission) -> str:
    # compile_execution_request already records an admission trace hash. This
    # helper intentionally derives the same canonical input independently so
    # the remediation binding can preserve the fresh admission provenance.
    import hashlib
    import json

    route = admission.resource_route
    payload = {
        "decision": admission.decision.value,
        "reasons": list(admission.reasons),
        "tenant_id": admission.request.tenant_id,
        "order_id": admission.request.order_id,
        "requested_sku": admission.request.requested_sku,
        "device_id": admission.request.device_id,
        "store_id": admission.request.store_id,
        "aisle": admission.request.aisle,
        "shelf": admission.request.shelf,
        "intent": admission.request.intent,
        "identity_status": admission.identity_status.value,
        "identity_confidence": admission.identity_confidence,
        "resource_route": {
            "decision": route.decision.value if route else None,
            "provider": route.provider if route else None,
            "region": route.region if route else None,
            "predicted_latency_ms": route.predicted_latency_ms if route else None,
            "reason": list(route.reason or ()) if route else [],
        },
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def prepare_remediation_execution(
    *,
    candidate: RemediationAdmissionCandidate,
    admission: PickAdmission,
    source_frame_id: str,
    evidence_signature: str,
    quantity: int = 1,
    capability_version: str,
    contract_version: str,
    request_id: str,
    secret: str | None = None,
    now: float | None = None,
    ttl_seconds: float = 30.0,
) -> RemediationExecutionAuthorization:
    """Prepare a fresh authorized remediation request for the existing executor.

    ``admission`` must be the result of a fresh call to the existing admission
    authority. The function never derives ALLOW from the candidate and never
    invokes an executor.
    """
    if candidate.authority != "admission-required":
        raise RemediationExecutionError("candidate_authority_invalid")
    if candidate.can_execute:
        raise RemediationExecutionError("candidate_must_not_be_executable")
    if not candidate.proposal_id or not candidate.proposal_hash or not candidate.candidate_hash:
        raise RemediationExecutionError("candidate_provenance_required")
    if admission.decision is not AdmissionDecision.ALLOW:
        raise RemediationExecutionError("remediation_execution_requires_fresh_allow_admission")
    if not source_frame_id or not evidence_signature:
        raise RemediationExecutionError("remediation_execution_evidence_required")

    plan = compile_execution_plan(
        admission=admission,
        source_frame_id=source_frame_id,
        evidence_signature=evidence_signature,
        quantity=quantity,
        capability_version=capability_version,
        contract_version=contract_version,
        operation=f"SHELF_SCOUTER_REMEDIATION:{candidate.action}",
    )

    signing_secret = secret if secret is not None else execution_signing_secret()
    request = compile_execution_request(
        admission=admission,
        request_id=request_id,
        source_frame_id=source_frame_id,
        evidence_signature=evidence_signature,
        plan_hash=plan.plan_hash,
        secret=signing_secret,
        now=now,
        ttl_seconds=ttl_seconds,
        capability_version=capability_version,
        contract_version=contract_version,
    )

    binding = RemediationExecutionBinding(
        schema=SCHEMA_VERSION,
        orchestrator_version=ORCHESTRATOR_VERSION,
        proposal_id=candidate.proposal_id,
        proposal_hash=candidate.proposal_hash,
        candidate_hash=candidate.candidate_hash,
        original_execution_id=candidate.execution_id,
        action=candidate.action,
        original_execution_boundary=dict(candidate.execution_boundary),
        new_admission_hash=_admission_hash(admission),
    )

    # Attach remediation provenance to the existing control-plane execution
    # trace. This is diagnostic provenance, not signed-request authority.
    from hoare_execution_request import attach_execution_provenance

    attach_execution_provenance(
        request.request_hash,
        {
            "remediation": binding.to_dict(),
        },
    )

    authorization = authorize_execution(
        request,
        secret=signing_secret,
        now=now,
        expected_tenant_id=admission.request.tenant_id,
        expected_device_id=admission.request.device_id,
    )

    return RemediationExecutionAuthorization(
        binding=binding,
        plan=plan,
        request=request,
        authorization=authorization,
    )


__all__ = [
    "ORCHESTRATOR_VERSION",
    "RemediationExecutionAuthorization",
    "RemediationExecutionBinding",
    "RemediationExecutionError",
    "SCHEMA_VERSION",
    "prepare_remediation_execution",
]
