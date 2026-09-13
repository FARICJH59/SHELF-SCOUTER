from hoare_debugging_agent import (
    DiagnosticDisposition,
    DiagnosticSeverity,
    HoareDebuggingAgent,
)


def test_healthy_execution_is_healthy():
    report = HoareDebuggingAgent().diagnose(
        session_id="s1",
        execution_id="e1",
        observations={"trusted_evidence": True, "execution_authorized": True},
        execution_result={"status": "completed", "latency_ms": 120},
    )

    assert report.disposition is DiagnosticDisposition.HEALTHY
    assert report.findings == ()
    assert report.metadata["authority"] == "diagnostic-only"
    assert report.metadata["can_execute"] is False


def test_execution_failure_becomes_investigate():
    report = HoareDebuggingAgent().diagnose(
        session_id="s1",
        execution_id="e2",
        observations={"evidence_refs": ["receipt:e2"]},
        execution_result={"status": "failed", "error": "adapter timeout"},
    )

    assert report.disposition is DiagnosticDisposition.INVESTIGATE
    assert report.findings[0].code == "EXECUTION_FAILURE"
    assert report.findings[0].severity is DiagnosticSeverity.ERROR
    assert report.findings[0].evidence_refs == ("receipt:e2",)


def test_missing_trust_boundary_escalates():
    report = HoareDebuggingAgent().diagnose(
        session_id="s1",
        observations={"trusted_evidence": False},
        execution_result={"status": "failed"},
    )

    assert report.disposition is DiagnosticDisposition.ESCALATE
    codes = {finding.code for finding in report.findings}
    assert "TRUST_BOUNDARY_MISSING" in codes


def test_unauthorized_execution_never_becomes_a_remediation_authority():
    report = HoareDebuggingAgent().diagnose(
        session_id="s1",
        execution_id="e3",
        observations={"execution_authorized": False},
        execution_result={"status": "completed"},
    )

    assert report.disposition is DiagnosticDisposition.ESCALATE
    assert report.metadata["can_execute"] is False
    assert all(
        action not in {"execute", "authorize", "approve"}
        for finding in report.findings
        for action in finding.proposed_actions
    )
