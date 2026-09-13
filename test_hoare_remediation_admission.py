"""Proposal-to-admission adapter tests.

Provenance: 2026-09-13.
"""

from dataclasses import replace

import pytest

from hoare_pick_admission import AdmissionDecision, PickRequest, ResourceRoute
from hoare_remediation_admission import (
    RemediationAdmissionError,
    admit_remediation_candidate,
    compile_remediation_admission_candidate,
)
from hoare_remediation_proposal import compile_remediation_proposal
from hoare_debugging_agent import (
    DiagnosticDisposition,
    DiagnosticFinding,
    DiagnosticSeverity,
    DebuggingReport,
)
from product_verification import verify_product


def _proposal(action: str = "revalidate_inputs"):
    report = DebuggingReport(
        schema="hoare.debugging-report.v1",
        debugger_version="1.0.0",
        session_id="session-1",
        execution_id="execution-1",
        disposition=DiagnosticDisposition.INVESTIGATE,
        findings=(
            DiagnosticFinding(
                code="EXECUTION_FAILURE",
                severity=DiagnosticSeverity.ERROR,
                message="adapter timeout",
                evidence_refs=("execution:execution-1",),
                proposed_actions=("inspect_execution_telemetry", "revalidate_inputs"),
            ),
        ),
        metadata={
            "authority": "diagnostic-only",
            "can_execute": False,
            "execution_boundary": {
                "request_hash": "request-hash",
                "plan_hash": "plan-hash",
                "receipt_hash": "receipt-hash",
            },
        },
    )
    return compile_remediation_proposal(
        report=report,
        proposal_id="proposal-1",
        action=action,
    )


def _request() -> PickRequest:
    return PickRequest(
        tenant_id="tenant-1",
        order_id="order-1",
        requested_sku="sku-1",
        device_id="device-1",
    )


def test_valid_proposal_becomes_non_executable_admission_candidate():
    candidate = compile_remediation_admission_candidate(
        proposal=_proposal(),
        request=_request(),
    )

    assert candidate.authority == "admission-required"
    assert candidate.can_execute is False
    assert candidate.request.intent == "hoare_remediation:revalidate_inputs"
    assert candidate.proposal_id == "proposal-1"
    assert candidate.proposal_hash
    assert candidate.candidate_hash
    assert candidate.execution_boundary["request_hash"] == "request-hash"


def test_tampered_proposal_hash_is_rejected():
    proposal = replace(_proposal(), proposal_hash="tampered")

    with pytest.raises(RemediationAdmissionError, match="proposal_hash_invalid"):
        compile_remediation_admission_candidate(
            proposal=proposal,
            request=_request(),
        )


def test_arbitrary_action_cannot_enter_this_admission_adapter():
    proposal = _proposal("revalidate_inputs")
    proposal = replace(proposal, action="execute_fix_now")
    # Rebuild the hash so the test proves the action allow-list is enforced,
    # rather than merely failing because the proposal was tampered with.
    unsigned = proposal.unsigned_payload()
    import hashlib
    import json

    proposal = replace(
        proposal,
        proposal_hash=hashlib.sha256(
            json.dumps(
                unsigned,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest(),
    )

    with pytest.raises(
        RemediationAdmissionError,
        match="proposal_action_not_supported_for_admission",
    ):
        compile_remediation_admission_candidate(
            proposal=proposal,
            request=_request(),
        )


def test_candidate_cannot_self_authorize():
    candidate = compile_remediation_admission_candidate(
        proposal=_proposal(),
        request=_request(),
    )
    tampered = replace(candidate, can_execute=True)

    identity = verify_product(
        requested_sku="sku-1",
        detected_sku="sku-1",
    )

    with pytest.raises(RemediationAdmissionError, match="candidate_must_not_be_executable"):
        admit_remediation_candidate(
            candidate=tampered,
            identity=identity,
        )


def test_provenance_survives_into_existing_admission_result():
    candidate = compile_remediation_admission_candidate(
        proposal=_proposal(),
        request=_request(),
    )
    identity = verify_product(
        requested_sku="sku-1",
        detected_sku="sku-1",
    )
    route = ResourceRoute(
        decision=AdmissionDecision.ALLOW,
        provider="test-provider",
        region="test-region",
    )

    admission = admit_remediation_candidate(
        candidate=candidate,
        identity=identity,
        resource_route=route,
    )

    assert admission.decision is AdmissionDecision.ALLOW
    assert admission.request.intent == "hoare_remediation:revalidate_inputs"
    assert admission.request.tenant_id == candidate.request.tenant_id
    assert admission.request.order_id == candidate.request.order_id
    assert admission.request.device_id == candidate.request.device_id
    assert admission.resource_route is route
