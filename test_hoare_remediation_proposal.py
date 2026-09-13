"""Remediation proposal boundary tests.

Provenance: 2026-09-13.
"""

import pytest

from hoare_debugging_agent import (
    DiagnosticDisposition,
    DiagnosticFinding,
    DiagnosticSeverity,
    DebuggingReport,
)
from hoare_remediation_proposal import (
    RemediationProposalError,
    compile_remediation_proposal,
)


def _report(disposition: DiagnosticDisposition) -> DebuggingReport:
    return DebuggingReport(
        schema="hoare.debugging-report.v1",
        debugger_version="1.0.0",
        session_id="session-1",
        execution_id="execution-1",
        disposition=disposition,
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


def test_proposal_is_non_executable_and_binds_diagnostic_evidence():
    proposal = compile_remediation_proposal(
        report=_report(DiagnosticDisposition.INVESTIGATE),
        proposal_id="proposal-1",
        action="inspect_execution_telemetry",
    )

    assert proposal.authority == "proposal-only"
    assert proposal.can_execute is False
    assert proposal.execution_id == "execution-1"
    assert proposal.proposal_hash
    assert proposal.execution_boundary["request_hash"] == "request-hash"
    assert proposal.evidence_refs == ("execution:execution-1",)


def test_unknown_action_cannot_be_promoted_from_diagnostic_report():
    with pytest.raises(RemediationProposalError, match="action_not_present"):
        compile_remediation_proposal(
            report=_report(DiagnosticDisposition.INVESTIGATE),
            proposal_id="proposal-2",
            action="execute_fix_now",
        )


def test_healthy_execution_cannot_create_remediation_proposal():
    with pytest.raises(RemediationProposalError, match="healthy_execution"):
        compile_remediation_proposal(
            report=_report(DiagnosticDisposition.HEALTHY),
            proposal_id="proposal-3",
            action="inspect_execution_telemetry",
        )
