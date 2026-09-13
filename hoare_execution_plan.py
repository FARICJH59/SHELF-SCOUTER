"""Server-authoritative execution-plan binding for SHELF-SCOUTER.

Design/provenance record: 2026-09-12.

Security invariant:

    client intent != execution plan
    admission != execution authorization
    execution plan != client-supplied provenance

The execution plan is constructed only after HOARE admission has produced
ALLOW. Its canonical representation is hashed and that hash becomes an
input to the cryptographically signed ExecutionRequest boundary.

This module deliberately does not call the plan PASOR. SHELF-SCOUTER does
not currently contain an authoritative PASOR producer, so this module creates
the server-side execution-plan provenance that actually exists.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from hoare_pick_admission import AdmissionDecision, PickAdmission


EXECUTION_PLAN_SCHEMA = "hoare.execution-plan.v1"
SHELF_SCOUTER_EXECUTION_PLAN_VERSION = "1.0.0"


class ExecutionPlanError(ValueError):
    """Raised when an execution plan cannot be safely constructed."""


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class ExecutionPlan:
    schema: str
    plan_version: str
    operation: str
    tenant_id: str
    order_id: str
    device_id: str
    intent: str
    requested_sku: str
    source_frame_id: str
    evidence_signature: str
    resource_provider: str
    resource_region: str
    capability_version: str
    contract_version: str
    quantity: int
    plan_hash: str

    def unsigned_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "plan_version": self.plan_version,
            "operation": self.operation,
            "tenant_id": self.tenant_id,
            "order_id": self.order_id,
            "device_id": self.device_id,
            "intent": self.intent,
            "requested_sku": self.requested_sku,
            "source_frame_id": self.source_frame_id,
            "evidence_signature": self.evidence_signature,
            "resource_provider": self.resource_provider,
            "resource_region": self.resource_region,
            "capability_version": self.capability_version,
            "contract_version": self.contract_version,
            "quantity": self.quantity,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self.unsigned_payload()
        payload["plan_hash"] = self.plan_hash
        return payload


def compile_execution_plan(
    *,
    admission: PickAdmission,
    source_frame_id: str,
    evidence_signature: str,
    quantity: int,
    capability_version: str,
    contract_version: str,
    operation: str = "SHELF_SCOUTER_PICK",
) -> ExecutionPlan:
    """Build the authoritative server-side plan after ALLOW admission."""

    if admission.decision is not AdmissionDecision.ALLOW:
        raise ExecutionPlanError("execution_plan_requires_allow_admission")

    if not source_frame_id:
        raise ExecutionPlanError("execution_plan_source_frame_required")

    if not evidence_signature:
        raise ExecutionPlanError("execution_plan_evidence_signature_required")

    if not capability_version or not contract_version:
        raise ExecutionPlanError("execution_plan_version_required")

    if not operation:
        raise ExecutionPlanError("execution_plan_operation_required")

    if not isinstance(quantity, int) or quantity < 1:
        raise ExecutionPlanError("execution_plan_quantity_invalid")

    route = admission.resource_route

    if route is None:
        raise ExecutionPlanError("execution_plan_resource_route_required")

    if route.decision is not AdmissionDecision.ALLOW:
        raise ExecutionPlanError("execution_plan_route_not_allowed")

    if not route.provider or not route.region:
        raise ExecutionPlanError("execution_plan_target_unbound")

    unsigned = {
        "schema": EXECUTION_PLAN_SCHEMA,
        "plan_version": SHELF_SCOUTER_EXECUTION_PLAN_VERSION,
        "operation": operation,
        "tenant_id": admission.request.tenant_id,
        "order_id": admission.request.order_id,
        "device_id": admission.request.device_id,
        "intent": admission.request.intent,
        "requested_sku": admission.request.requested_sku,
        "source_frame_id": source_frame_id,
        "evidence_signature": evidence_signature,
        "resource_provider": route.provider,
        "resource_region": route.region,
        "capability_version": capability_version,
        "contract_version": contract_version,
        "quantity": quantity,
    }

    plan_hash = _sha256(unsigned)

    return ExecutionPlan(
        **unsigned,
        plan_hash=plan_hash,
    )


def verify_execution_plan(plan: ExecutionPlan) -> bool:
    """Verify that the plan hash still represents its canonical payload."""

    expected = _sha256(plan.unsigned_payload())

    return expected == plan.plan_hash
