"""Tests for the additive HOARE debugging telemetry adapter.

Provenance: 2026-09-13.
"""

import pytest

from execution_feedback import ExecutionFeedbackRecorder
from hoare_debugging_agent import DiagnosticDisposition
from hoare_debugging_runtime import HoareDebuggingRuntime
from hoare_pick_admission import AdmissionDecision, PickRequest, ResourceRoute
from hoare_remediation_coordinator import RemediationCoordinatorError
from product_verification import verify_product


SECRET = "runtime-test-remediation-key"


@pytest.fixture
def recorder() -> ExecutionFeedbackRecorder:
    return ExecutionFeedbackRecorder()


def _start(recorder: ExecutionFeedbackRecorder):
    return recorder.start(
        tenant_id="tenant-1",
        order_id="order-1",
        requested_sku="SKU-123",
        provider="test-provider",
        region="test-region",
        device_id="device-1",
        model="test-model",
    )


def _request() -> PickRequest:
    return PickRequest(
        tenant_id="tenant-1",
        order_id="order-1",
        requested_sku="SKU-123",
        device_id="device-1",
    )


def _route(decision=AdmissionDecision.ALLOW) -> ResourceRoute:
    return ResourceRoute(
        decision=decision,
        provider="test-provider",
        region="test-region",
    )


def test_runtime_maps_success_to_healthy(recorder: ExecutionFeedbackRecorder) -> None:
    record = _start(recorder)
    recorder.complete(
        record.execution_id,
        success=True,
        identity_status="VERIFIED",
        identity_confidence=0.99,
    )

    report = HoareDebuggingRuntime().diagnose_execution(
        recorder,
        execution_id=record.execution_id,
        session_id="session-1",
        trusted_evidence=True,
        execution_authorized=True,
        evidence_refs=("evidence:1",),
    )

    assert report.disposition == DiagnosticDisposition.HEALTHY
    assert report.execution_id == record.execution_id
    assert report.metadata["authority"] == "diagnostic-only"
    assert report.metadata["can_execute"] is False


def test_runtime_maps_failure_to_investigate(recorder: ExecutionFeedbackRecorder) -> None:
    record = _start(recorder)
    recorder.complete(
        record.execution_id,
        success=False,
        identity_status="UNVERIFIED",
        error="identity mismatch",
    )

    report = HoareDebuggingRuntime().diagnose_execution(
        recorder,
        execution_id=record.execution_id,
        session_id="session-2",
        trusted_evidence=True,
        execution_authorized=True,
    )

    assert report.disposition == DiagnosticDisposition.INVESTIGATE
    assert any(f.code == "EXECUTION_FAILURE" for f in report.findings)


def test_runtime_maps_missing_trust_to_escalate(recorder: ExecutionFeedbackRecorder) -> None:
    record = _start(recorder)
    recorder.complete(record.execution_id, success=False, error="blocked")

    report = HoareDebuggingRuntime().diagnose_execution(
        recorder,
        execution_id=record.execution_id,
        session_id="session-3",
        trusted_evidence=False,
        execution_authorized=False,
    )

    assert report.disposition == DiagnosticDisposition.ESCALATE
    assert {f.code for f in report.findings} >= {
        "TRUST_BOUNDARY_MISSING",
        "EXECUTION_NOT_AUTHORIZED",
        "EXECUTION_FAILURE",
    }


def test_runtime_does_not_accept_unknown_execution(recorder: ExecutionFeedbackRecorder) -> None:
    with pytest.raises(KeyError, match="Unknown execution_id"):
        HoareDebuggingRuntime().diagnose_execution(
            recorder,
            execution_id="missing",
            session_id="session-4",
        )


def test_runtime_can_build_non_executable_remediation_candidate(
    recorder: ExecutionFeedbackRecorder,
) -> None:
    record = _start(recorder)
    recorder.complete(
        record.execution_id,
        success=False,
        identity_status="UNVERIFIED",
        error="identity mismatch",
    )

    runtime = HoareDebuggingRuntime()
    report = runtime.diagnose_execution(
        recorder,
        execution_id=record.execution_id,
        session_id="session-5",
        trusted_evidence=True,
        execution_authorized=True,
        evidence_refs=("evidence:5",),
    )

    candidate = runtime.propose_remediation_candidate(
        report,
        proposal_id="proposal-runtime-1",
        action="revalidate_inputs",
        request=_request(),
    )

    assert candidate.authority == "admission-required"
    assert candidate.can_execute is False
    assert candidate.proposal_id == "proposal-runtime-1"
    assert candidate.execution_id == record.execution_id
    assert candidate.request().intent == "hoare_remediation:revalidate_inputs"


def test_runtime_prepares_fresh_governed_remediation_without_execution(
    recorder: ExecutionFeedbackRecorder,
) -> None:
    record = _start(recorder)
    recorder.complete(
        record.execution_id,
        success=False,
        identity_status="UNVERIFIED",
        error="identity mismatch",
    )

    runtime = HoareDebuggingRuntime()
    report = runtime.diagnose_execution(
        recorder,
        execution_id=record.execution_id,
        session_id="session-remediation",
        trusted_evidence=True,
        execution_authorized=True,
        evidence_refs=("evidence:remediation",),
    )
    candidate = runtime.propose_remediation_candidate(
        report,
        proposal_id="proposal-runtime-2",
        action="revalidate_inputs",
        request=_request(),
    )

    identity = verify_product(requested_sku="SKU-123", detected_sku="SKU-123")
    preparation = runtime.prepare_remediation_execution(
        candidate=candidate,
        identity=identity,
        source_frame_id="frame-remediation",
        evidence_signature="evidence-signature",
        capability_version="1.0.0",
        contract_version="1.0.0",
        request_id="runtime-remediation-request-1",
        secret=SECRET,
        resource_route=_route(),
        now=1000.0,
    )

    assert preparation.admission.decision is AdmissionDecision.ALLOW
    assert preparation.execution.allowed is True
    assert preparation.execution.request.request_id == "runtime-remediation-request-1"
    assert preparation.execution.request.plan_hash == preparation.execution.plan.plan_hash
    assert preparation.execution.binding.proposal_id == candidate.proposal_id
    assert preparation.execution.binding.original_execution_id == record.execution_id
    assert preparation.execution.binding.authority == "signed-execution-required"
    assert preparation.execution.binding.can_execute is False


def test_runtime_remediation_reenters_admission_and_stops_on_deny(
    recorder: ExecutionFeedbackRecorder,
) -> None:
    record = _start(recorder)
    recorder.complete(
        record.execution_id,
        success=False,
        identity_status="UNVERIFIED",
        error="identity mismatch",
    )

    runtime = HoareDebuggingRuntime()
    report = runtime.diagnose_execution(
        recorder,
        execution_id=record.execution_id,
        session_id="session-remediation-deny",
        trusted_evidence=True,
        execution_authorized=True,
    )
    candidate = runtime.propose_remediation_candidate(
        report,
        proposal_id="proposal-runtime-3",
        action="revalidate_inputs",
        request=_request(),
    )

    identity = verify_product(requested_sku="SKU-123", detected_sku="SKU-123")

    with pytest.raises(
        RemediationCoordinatorError,
        match="remediation_execution_requires_fresh_allow_admission",
    ):
        runtime.prepare_remediation_execution(
            candidate=candidate,
            identity=identity,
            source_frame_id="frame-remediation-deny",
            evidence_signature="evidence-signature",
            capability_version="1.0.0",
            contract_version="1.0.0",
            request_id="runtime-remediation-request-2",
            secret=SECRET,
            resource_route=_route(AdmissionDecision.DENY),
            now=1000.0,
        )
