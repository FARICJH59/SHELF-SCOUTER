"""Governed remediation execution orchestration tests.

Provenance: 2026-09-13.
"""

from dataclasses import replace

import pytest

from hoare_execution_request import _EXECUTION_TRACE
from hoare_pick_admission import AdmissionDecision, PickRequest, ResourceRoute, admit_pick
from hoare_remediation_admission import compile_remediation_admission_candidate
from hoare_remediation_execution import (
    RemediationExecutionError,
    prepare_remediation_execution,
)
from hoare_remediation_proposal import compile_remediation_proposal
from hoare_debugging_agent import (
    DiagnosticDisposition,
    DiagnosticFinding,
    DiagnosticSeverity,
    DebuggingReport,
)
from product_verification import verify_product


SECRET = "remediation-test-secret"


def _candidate():
    report = DebuggingReport(
        schema="hoare.debugging-report.v1",
        debugger_version="1.0.0",
        session_id="session-1",
        execution_id="execution-original",
        disposition=DiagnosticDisposition.INVESTIGATE,
        findings=(
            DiagnosticFinding(
                code="EXECUTION_FAILURE",
                severity=DiagnosticSeverity.ERROR,
                message="execution failed",
                evidence_refs=("execution:execution-original",),
                proposed_actions=("revalidate_inputs",),
            ),
        ),
        metadata={
            "authority": "diagnostic-only",
            "can_execute": False,
            "execution_boundary": {
                "request_hash": "original-request",
                "plan_hash": "original-plan",
                "receipt_hash": "original-receipt",
            },
        },
    )
    proposal = compile_remediation_proposal(
        report=report,
        proposal_id="proposal-1",
        action="revalidate_inputs",
    )
    return compile_remediation_admission_candidate(
        proposal=proposal,
        request=PickRequest(
            tenant_id="tenant-1",
            order_id="order-1",
            requested_sku="sku-1",
            device_id="device-1",
        ),
    )


def _allow_admission():
    identity = verify_product(
        requested_sku="sku-1",
        detected_sku="sku-1",
    )
    route = ResourceRoute(
        decision=AdmissionDecision.ALLOW,
        provider="test-provider",
        region="test-region",
    )
    return admit_pick(
        _candidate().request(),
        identity,
        resource_route=route,
    )


def test_deny_cannot_enter_remediation_execution():
    candidate = _candidate()
    admission = replace(_allow_admission(), decision=AdmissionDecision.DENY)

    with pytest.raises(
        RemediationExecutionError,
        match="remediation_execution_requires_fresh_allow_admission",
    ):
        prepare_remediation_execution(
            candidate=candidate,
            admission=admission,
            source_frame_id="frame-remediation",
            evidence_signature="evidence-signature",
            capability_version="1.0.0",
            contract_version="1.0.0",
            request_id="remediation-request-1",
            secret=SECRET,
            now=1000.0,
        )


def test_escalate_cannot_enter_remediation_execution():
    candidate = _candidate()
    admission = replace(_allow_admission(), decision=AdmissionDecision.ESCALATE)

    with pytest.raises(
        RemediationExecutionError,
        match="remediation_execution_requires_fresh_allow_admission",
    ):
        prepare_remediation_execution(
            candidate=candidate,
            admission=admission,
            source_frame_id="frame-remediation",
            evidence_signature="evidence-signature",
            capability_version="1.0.0",
            contract_version="1.0.0",
            request_id="remediation-request-2",
            secret=SECRET,
            now=1000.0,
        )


def test_allow_creates_fresh_plan_request_and_authorization():
    candidate = _candidate()
    admission = _allow_admission()

    result = prepare_remediation_execution(
        candidate=candidate,
        admission=admission,
        source_frame_id="frame-remediation",
        evidence_signature="evidence-signature",
        capability_version="1.0.0",
        contract_version="1.0.0",
        request_id="remediation-request-3",
        secret=SECRET,
        now=1000.0,
    )

    assert result.allowed is True
    assert result.authorization.allowed is True
    assert result.plan.operation == "SHELF_SCOUTER_REMEDIATION:revalidate_inputs"
    assert result.plan.plan_hash
    assert result.request.request_hash
    assert result.request.request_hash != "original-request"
    assert result.request.plan_hash == result.plan.plan_hash
    assert result.binding.proposal_id == "proposal-1"
    assert result.binding.candidate_hash == candidate.candidate_hash
    assert result.binding.original_execution_id == "execution-original"
    assert result.binding.new_admission_hash
    assert result.binding.can_execute is False


def test_remediation_request_is_fresh_and_does_not_inherit_old_authorization():
    candidate = _candidate()
    admission = _allow_admission()

    result = prepare_remediation_execution(
        candidate=candidate,
        admission=admission,
        source_frame_id="frame-remediation",
        evidence_signature="new-evidence-signature",
        capability_version="1.0.0",
        contract_version="1.0.0",
        request_id="remediation-request-4",
        secret=SECRET,
        now=1000.0,
    )

    assert result.request.request_id == "remediation-request-4"
    assert result.request.evidence_signature == "new-evidence-signature"
    assert result.authorization.request_hash == result.request.request_hash
    assert result.authorization.authorized_at == 1000.0
    assert result.binding.original_execution_boundary["request_hash"] == "original-request"


def test_remediation_provenance_is_bound_to_internal_execution_trace():
    candidate = _candidate()
    admission = _allow_admission()

    result = prepare_remediation_execution(
        candidate=candidate,
        admission=admission,
        source_frame_id="frame-remediation",
        evidence_signature="evidence-signature",
        capability_version="1.0.0",
        contract_version="1.0.0",
        request_id="remediation-request-5",
        secret=SECRET,
        now=1000.0,
    )

    trace = _EXECUTION_TRACE[result.request.request_hash]
    remediation = trace["remediation"]

    assert remediation["proposal_id"] == "proposal-1"
    assert remediation["candidate_hash"] == candidate.candidate_hash
    assert remediation["original_execution_id"] == "execution-original"
    assert remediation["new_admission_hash"] == result.binding.new_admission_hash
    assert remediation["can_execute"] is False


def test_executable_candidate_is_rejected_before_plan_creation():
    candidate = replace(_candidate(), can_execute=True)

    with pytest.raises(RemediationExecutionError, match="candidate_must_not_be_executable"):
        prepare_remediation_execution(
            candidate=candidate,
            admission=_allow_admission(),
            source_frame_id="frame-remediation",
            evidence_signature="evidence-signature",
            capability_version="1.0.0",
            contract_version="1.0.0",
            request_id="remediation-request-6",
            secret=SECRET,
            now=1000.0,
        )
