from __future__ import annotations

import pytest

from hoare_execution_request import (
    ExecutionRequestError,
    authorize_execution,
    compile_execution_request,
    create_execution_receipt,
)
from hoare_pick_admission import AdmissionDecision, PickAdmission, PickRequest, ResourceRoute
from product_verification import IdentityStatus


SECRET = "test-execution-secret"


def _allow_admission() -> PickAdmission:
    request = PickRequest(
        tenant_id="tenant-1",
        order_id="order-1",
        requested_sku="SKU-1",
        device_id="device-1",
        store_id="store-1",
        intent="customer_order_pick",
    )
    route = ResourceRoute(
        decision=AdmissionDecision.ALLOW,
        provider="edge",
        region="edge-local",
        reason=["hoare_resource_authority"],
    )
    return PickAdmission(
        decision=AdmissionDecision.ALLOW,
        reasons=["product_identity_verified", "resource_route_accepted"],
        request=request,
        identity_status=IdentityStatus.VERIFIED,
        identity_confidence=1.0,
        resource_route=route,
    )


def test_compile_requires_allow():
    admission = _allow_admission()
    denied = PickAdmission(
        decision=AdmissionDecision.ESCALATE,
        reasons=["product_identity_not_verified"],
        request=admission.request,
        identity_status=IdentityStatus.INFERRED,
        identity_confidence=0.5,
        resource_route=admission.resource_route,
    )

    with pytest.raises(ExecutionRequestError, match="requires_allow"):
        compile_execution_request(
            admission=denied,
            request_id="req-1",
            source_frame_id="frame-1",
            evidence_signature="evidence-sig",
            plan_hash="plan-hash",
            secret=SECRET,
            now=100.0,
        )


def test_compile_binds_request_and_target():
    request = compile_execution_request(
        admission=_allow_admission(),
        request_id="req-1",
        source_frame_id="frame-1",
        evidence_signature="evidence-sig",
        plan_hash="plan-hash",
        secret=SECRET,
        now=100.0,
        ttl_seconds=30,
    )

    assert request.schema == "hoare.execution-request.v1"
    assert request.admission_decision == "ALLOW"
    assert request.resource_provider == "edge"
    assert request.resource_region == "edge-local"
    assert request.expires_at == 130.0
    assert len(request.request_hash) == 64
    assert len(request.signature) == 64


def test_edge_authorization_accepts_valid_request():
    request = compile_execution_request(
        admission=_allow_admission(),
        request_id="req-1",
        source_frame_id="frame-1",
        evidence_signature="evidence-sig",
        plan_hash="plan-hash",
        secret=SECRET,
        now=100.0,
    )

    authorization = authorize_execution(
        request,
        secret=SECRET,
        now=110.0,
        expected_tenant_id="tenant-1",
        expected_device_id="device-1",
    )

    assert authorization.allowed is True
    assert authorization.reasons == ("execution_request_authorized",)


def test_edge_authorization_rejects_expired_request():
    request = compile_execution_request(
        admission=_allow_admission(),
        request_id="req-1",
        source_frame_id="frame-1",
        evidence_signature="evidence-sig",
        plan_hash="plan-hash",
        secret=SECRET,
        now=100.0,
        ttl_seconds=10,
    )

    authorization = authorize_execution(request, secret=SECRET, now=110.0)
    assert authorization.allowed is False
    assert "execution_request_expired" in authorization.reasons


def test_edge_authorization_rejects_tampering():
    request = compile_execution_request(
        admission=_allow_admission(),
        request_id="req-1",
        source_frame_id="frame-1",
        evidence_signature="evidence-sig",
        plan_hash="plan-hash",
        secret=SECRET,
        now=100.0,
    )
    tampered = request.__class__(
        **{**request.to_dict(), "requested_sku": "SKU-TAMPERED"}
    )

    authorization = authorize_execution(tampered, secret=SECRET, now=110.0)
    assert authorization.allowed is False
    assert "execution_request_hash_mismatch" in authorization.reasons
    assert "execution_request_signature_invalid" in authorization.reasons


def test_edge_authorization_binds_tenant_and_device():
    request = compile_execution_request(
        admission=_allow_admission(),
        request_id="req-1",
        source_frame_id="frame-1",
        evidence_signature="evidence-sig",
        plan_hash="plan-hash",
        secret=SECRET,
        now=100.0,
    )

    authorization = authorize_execution(
        request,
        secret=SECRET,
        now=110.0,
        expected_tenant_id="wrong-tenant",
        expected_device_id="wrong-device",
    )

    assert authorization.allowed is False
    assert "execution_request_tenant_mismatch" in authorization.reasons
    assert "execution_request_device_mismatch" in authorization.reasons


def test_receipt_is_bound_to_request_hash():
    request = compile_execution_request(
        admission=_allow_admission(),
        request_id="req-1",
        source_frame_id="frame-1",
        evidence_signature="evidence-sig",
        plan_hash="plan-hash",
        secret=SECRET,
        now=100.0,
    )

    receipt = create_execution_receipt(
        request=request,
        execution_id="exec-1",
        status="SUCCEEDED",
        result={"picked": True, "quantity": 1},
        secret=SECRET,
        observed_at=111.0,
    )

    assert receipt.request_hash == request.request_hash
    assert receipt.schema == "hoare.execution-receipt.v1"
    assert len(receipt.result_hash) == 64
    assert len(receipt.signature) == 64


def test_compile_rejects_unbound_execution_target():
    admission = _allow_admission()
    admission = PickAdmission(
        decision=admission.decision,
        reasons=admission.reasons,
        request=admission.request,
        identity_status=admission.identity_status,
        identity_confidence=admission.identity_confidence,
        resource_route=ResourceRoute(
            decision=AdmissionDecision.ALLOW,
            provider=None,
            region=None,
            reason=["bad-route"],
        ),
    )

    with pytest.raises(ExecutionRequestError, match="target_unbound"):
        compile_execution_request(
            admission=admission,
            request_id="req-1",
            source_frame_id="frame-1",
            evidence_signature="evidence-sig",
            plan_hash="plan-hash",
            secret=SECRET,
            now=100.0,
        )
