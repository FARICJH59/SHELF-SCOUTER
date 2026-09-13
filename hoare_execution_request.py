"""Hash-bound execution request boundary for SHELF-SCOUTER.

Design/provenance record: 2026-09-12.

Security invariant:
    HOARE admission != executable command.

This module converts an already-ALLOWed pick admission into a canonical,
cryptographically bound execution request. It does not perform the physical
execution itself. The request binds tenant/order/device/intent, requested SKU,
source frame, trusted evidence signature, resource route, capability version,
plan hash, and expiration. A separate authorization step verifies the request
before execution.

The module is intentionally provider-neutral and uses only the Python standard
library so the boundary can run on phone gateways, edge nodes, or control
planes without a new runtime dependency.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Mapping

from hoare_pick_admission import AdmissionDecision, PickAdmission


EXECUTION_REQUEST_SCHEMA = "hoare.execution-request.v1"
EXECUTION_RECEIPT_SCHEMA = "hoare.execution-receipt.v1"
SHELF_SCOUTER_CONTRACT_VERSION = "1.0.0"
VISION_CAPABILITY_VERSION = "1.0.0"
DEFAULT_TTL_SECONDS = 30.0
MAX_TTL_SECONDS = 300.0

# Diagnostic-only trace state. This is deliberately outside the signed request
# payload so debugging provenance cannot alter execution authority.
_EXECUTION_TRACE: dict[str, dict[str, Any]] = {}


class ExecutionRequestError(ValueError):
    """Raised when an execution request cannot be safely constructed."""


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256_hex(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _hmac_hex(secret: str, payload: Mapping[str, Any]) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        _canonical_json(payload),
        hashlib.sha256,
    ).hexdigest()


def _admission_trace_hash(admission: PickAdmission) -> str:
    """Hash the admission decision as diagnostic provenance only."""
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
    return _sha256_hex(payload)


@dataclass(frozen=True)
class ExecutionRequest:
    schema: str
    request_id: str
    issued_at: float
    expires_at: float
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
    plan_hash: str
    admission_decision: str
    request_hash: str
    signature: str

    def unsigned_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "request_id": self.request_id,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
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
            "plan_hash": self.plan_hash,
            "admission_decision": self.admission_decision,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self.unsigned_payload()
        payload["request_hash"] = self.request_hash
        payload["signature"] = self.signature
        return payload


@dataclass(frozen=True)
class ExecutionAuthorization:
    allowed: bool
    reasons: tuple[str, ...]
    request_hash: str
    authorized_at: float


@dataclass(frozen=True)
class ExecutionReceipt:
    schema: str
    request_hash: str
    execution_id: str
    status: str
    observed_at: float
    result_hash: str
    signature: str

    def unsigned_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "request_hash": self.request_hash,
            "execution_id": self.execution_id,
            "status": self.status,
            "observed_at": self.observed_at,
            "result_hash": self.result_hash,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self.unsigned_payload()
        payload["signature"] = self.signature
        return payload


def compile_execution_request(
    *,
    admission: PickAdmission,
    request_id: str,
    source_frame_id: str,
    evidence_signature: str,
    plan_hash: str,
    secret: str,
    now: float | None = None,
    ttl_seconds: float = DEFAULT_TTL_SECONDS,
    capability_version: str = VISION_CAPABILITY_VERSION,
    contract_version: str = SHELF_SCOUTER_CONTRACT_VERSION,
) -> ExecutionRequest:
    """Compile an ALLOW admission into a signed, expiring execution request."""
    if admission.decision is not AdmissionDecision.ALLOW:
        raise ExecutionRequestError("execution_request_requires_allow_admission")
    if not secret:
        raise ExecutionRequestError("execution_signing_secret_required")
    if not request_id or not source_frame_id or not evidence_signature or not plan_hash:
        raise ExecutionRequestError("execution_request_binding_fields_required")
    if not capability_version or not contract_version:
        raise ExecutionRequestError("execution_request_version_required")
    if not admission.resource_route:
        raise ExecutionRequestError("execution_request_resource_route_required")
    route = admission.resource_route
    if route.decision is not AdmissionDecision.ALLOW:
        raise ExecutionRequestError("execution_request_route_not_allowed")
    if not route.provider or not route.region:
        raise ExecutionRequestError("execution_request_target_unbound")

    ttl = float(ttl_seconds)
    if ttl <= 0 or ttl > MAX_TTL_SECONDS:
        raise ExecutionRequestError("execution_request_ttl_invalid")

    issued_at = float(time.time() if now is None else now)
    expires_at = issued_at + ttl

    unsigned = {
        "schema": EXECUTION_REQUEST_SCHEMA,
        "request_id": request_id,
        "issued_at": issued_at,
        "expires_at": expires_at,
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
        "plan_hash": plan_hash,
        "admission_decision": admission.decision.value,
    }
    request_hash = _sha256_hex(unsigned)
    signature = _hmac_hex(secret, unsigned)
    request = ExecutionRequest(
        **unsigned,
        request_hash=request_hash,
        signature=signature,
    )

    _EXECUTION_TRACE[request_hash] = {
        "trace_version": "hoare.execution-trace.v1",
        "request_id": request.request_id,
        "request_hash": request.request_hash,
        "admission_hash": _admission_trace_hash(admission),
        "admission_decision": admission.decision.value,
        "evidence_signature": evidence_signature,
        "plan_hash": plan_hash,
        "authorization": None,
    }
    return request


def authorize_execution(
    request: ExecutionRequest,
    *,
    secret: str,
    now: float | None = None,
    expected_tenant_id: str | None = None,
    expected_device_id: str | None = None,
) -> ExecutionAuthorization:
    """Re-authorize a request immediately before execution.

    This is deliberately independent of request construction. An edge executor
    can verify the request without trusting the caller that created it.
    """
    current = float(time.time() if now is None else now)
    reasons: list[str] = []

    if not secret:
        return ExecutionAuthorization(False, ("execution_signing_secret_required",), request.request_hash, current)

    unsigned = request.unsigned_payload()
    expected_hash = _sha256_hex(unsigned)
    if not hmac.compare_digest(expected_hash, request.request_hash):
        reasons.append("execution_request_hash_mismatch")

    expected_signature = _hmac_hex(secret, unsigned)
    if not hmac.compare_digest(expected_signature, request.signature):
        reasons.append("execution_request_signature_invalid")

    if request.admission_decision != AdmissionDecision.ALLOW.value:
        reasons.append("execution_request_not_allow")

    if current >= request.expires_at:
        reasons.append("execution_request_expired")

    if expected_tenant_id is not None and request.tenant_id != expected_tenant_id:
        reasons.append("execution_request_tenant_mismatch")

    if expected_device_id is not None and request.device_id != expected_device_id:
        reasons.append("execution_request_device_mismatch")

    authorization = ExecutionAuthorization(
        allowed=not reasons,
        reasons=tuple(reasons) if reasons else ("execution_request_authorized",),
        request_hash=request.request_hash,
        authorized_at=current,
    )
    trace = _EXECUTION_TRACE.setdefault(request.request_hash, {
        "trace_version": "hoare.execution-trace.v1",
        "request_id": request.request_id,
        "request_hash": request.request_hash,
        "plan_hash": request.plan_hash,
        "evidence_signature": request.evidence_signature,
        "authorization": None,
    })
    trace["authorization"] = {
        "allowed": authorization.allowed,
        "reasons": list(authorization.reasons),
        "authorized_at": authorization.authorized_at,
    }
    return authorization


def create_execution_receipt(
    *,
    request: ExecutionRequest,
    execution_id: str,
    status: str,
    result: Mapping[str, Any],
    secret: str,
    observed_at: float | None = None,
) -> ExecutionReceipt:
    """Create a signed receipt bound to the exact authorized request hash."""
    if not execution_id or not status:
        raise ExecutionRequestError("execution_receipt_fields_required")
    if not secret:
        raise ExecutionRequestError("execution_signing_secret_required")
    if not isinstance(result, Mapping):
        raise ExecutionRequestError("execution_receipt_result_invalid")

    timestamp = float(time.time() if observed_at is None else observed_at)
    result_hash = hashlib.sha256(_canonical_json(dict(result))).hexdigest()
    unsigned = {
        "schema": EXECUTION_RECEIPT_SCHEMA,
        "request_hash": request.request_hash,
        "execution_id": execution_id,
        "status": status,
        "observed_at": timestamp,
        "result_hash": result_hash,
    }
    signature = _hmac_hex(secret, unsigned)
    receipt = ExecutionReceipt(
        **unsigned,
        signature=signature,
    )

    receipt_hash = hashlib.sha256(_canonical_json(unsigned)).hexdigest()
    trace = dict(_EXECUTION_TRACE.get(request.request_hash, {}))
    trace.update({
        "receipt_hash": receipt_hash,
        "receipt_signature": receipt.signature,
        "receipt_schema": receipt.schema,
        "execution_id": execution_id,
    })

    # Bridge into the already-created diagnostic report without importing the
    # recorder at module import time. This avoids a circular dependency and
    # keeps the execution boundary authoritative and provider-neutral.
    try:
        from execution_feedback import ExecutionFeedbackRecorder

        ExecutionFeedbackRecorder.attach_execution_boundary(execution_id, trace)
    except Exception:
        # Diagnostic enrichment is best-effort telemetry. It must never turn a
        # valid signed receipt into an execution failure.
        pass

    return receipt


def execution_signing_secret() -> str:
    """Read the production execution signing secret without exposing it."""
    return os.getenv("HOARE_EXECUTION_SIGNING_KEY", "").strip()
