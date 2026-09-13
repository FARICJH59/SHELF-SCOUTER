"""Execution telemetry to HOARE diagnostics integration tests.

Provenance: 2026-09-13.
"""

from execution_feedback import ExecutionFeedbackRecorder
from hoare_debugging_agent import DiagnosticDisposition
from hoare_execution_plan import compile_execution_plan
from hoare_execution_request import (
    authorize_execution,
    compile_execution_request,
    create_execution_receipt,
)
from hoare_pick_admission import AdmissionDecision, PickAdmission, PickRequest, ResourceRoute
from product_verification import IdentityStatus


TEST_SECRET = "shelf-scouter-test-key-20260913"


def test_complete_persists_diagnostic_report_without_changing_execution_result():
    recorder = ExecutionFeedbackRecorder()
    execution = recorder.start(
        tenant_id="tenant-1",
        order_id="order-1",
        requested_sku="SKU-123",
        provider="edge",
        region="edge-local",
        device_id="device-1",
        model="targeted-vision",
    )

    completed = recorder.complete(
        execution.execution_id,
        success=False,
        identity_status="UNVERIFIED",
        identity_confidence=0.21,
        error="adapter timeout",
    )

    report = recorder.diagnostic_report(execution.execution_id)

    assert completed.success is False
    assert completed.error == "adapter timeout"
    assert report is not None
    assert report.execution_id == execution.execution_id
    assert report.disposition is DiagnosticDisposition.INVESTIGATE
    assert report.metadata["authority"] == "diagnostic-only"
    assert report.metadata["can_execute"] is False
    assert report.findings[0].code == "EXECUTION_FAILURE"


def test_diagnostic_snapshot_is_internal_and_does_not_modify_execution_snapshot():
    recorder = ExecutionFeedbackRecorder()
    execution = recorder.start(
        tenant_id="tenant-1",
        order_id="order-2",
        requested_sku="SKU-456",
        provider="edge",
        region="edge-local",
        device_id="device-2",
        model="targeted-vision",
    )
    recorder.complete(execution.execution_id, success=True)

    assert len(recorder.snapshot()) == 1
    assert len(recorder.diagnostic_snapshot()) == 1
    assert recorder.snapshot()[0].execution_id == execution.execution_id
    assert recorder.diagnostic_snapshot()[0].execution_id == execution.execution_id


def test_signed_execution_trace_enriches_diagnostic_report_after_receipt():
    recorder = ExecutionFeedbackRecorder()
    execution = recorder.start(
        tenant_id="tenant-1",
        order_id="order-trace",
        requested_sku="SKU-TRACE",
        provider="edge",
        region="edge-local",
        device_id="device-trace",
        model="targeted-vision",
    )

    admission = PickAdmission(
        decision=AdmissionDecision.ALLOW,
        reasons=["product_identity_verified", "resource_route_accepted"],
        request=PickRequest(
            tenant_id="tenant-1",
            order_id="order-trace",
            requested_sku="SKU-TRACE",
            device_id="device-trace",
        ),
        identity_status=IdentityStatus.VERIFIED,
        identity_confidence=0.99,
        resource_route=ResourceRoute(
            decision=AdmissionDecision.ALLOW,
            provider="edge",
            region="edge-local",
            reason=["route_accepted"],
        ),
    )

    plan = compile_execution_plan(
        admission=admission,
        source_frame_id="frame-trace",
        evidence_signature="evidence-signature-trace",
        quantity=1,
        capability_version="1.0.0",
        contract_version="1.0.0",
    )

    execution_request = compile_execution_request(
        admission=admission,
        request_id="request-trace",
        source_frame_id="frame-trace",
        evidence_signature="evidence-signature-trace",
        plan_hash=plan.plan_hash,
        secret=TEST_SECRET,
        now=1000.0,
    )

    authorization = authorize_execution(
        execution_request,
        secret=TEST_SECRET,
        now=1001.0,
        expected_tenant_id="tenant-1",
        expected_device_id="device-trace",
    )
    assert authorization.allowed is True

    completed = recorder.complete(
        execution.execution_id,
        success=True,
        identity_status="VERIFIED",
        identity_confidence=0.99,
    )

    receipt = create_execution_receipt(
        request=execution_request,
        execution_id=completed.execution_id,
        status="SUCCEEDED",
        result={"execution_id": completed.execution_id, "latency_ms": completed.latency_ms},
        secret=TEST_SECRET,
        observed_at=1002.0,
    )

    report = recorder.diagnostic_report(execution.execution_id)
    assert report is not None
    trace = report.metadata["execution_boundary"]

    assert trace["trace_version"] == "hoare.execution-trace.v1"
    assert trace["request_id"] == execution_request.request_id
    assert trace["request_hash"] == execution_request.request_hash
    assert trace["admission_hash"]
    assert trace["admission_decision"] == "ALLOW"
    assert trace["evidence_signature"] == "evidence-signature-trace"
    assert trace["plan_hash"] == plan.plan_hash
    assert trace["authorization"]["allowed"] is True
    assert trace["execution_id"] == completed.execution_id
    assert trace["receipt_hash"]
    assert trace["receipt_signature"] == receipt.signature

    # The customer-facing execution result remains unchanged.
    assert completed.success is True
    assert completed.execution_id == execution.execution_id
