"""Runtime adapter from SHELF-SCOUTER execution telemetry to HOARE diagnostics.

Provenance: 2026-09-13.

This adapter is intentionally additive. It observes the existing
ExecutionFeedbackRecorder and delegates classification to HoareDebuggingAgent.
It never authorizes, executes, retries, mutates execution state, or replaces
the signed execution boundary.
"""

from __future__ import annotations

from typing import Any, Mapping

from execution_feedback import ExecutionFeedbackRecorder, PickExecution
from hoare_debugging_agent import DebuggingReport, HoareDebuggingAgent
from hoare_pick_admission import PickRequest
from hoare_remediation_admission import (
    RemediationAdmissionCandidate,
    compile_remediation_admission_candidate,
)
from hoare_remediation_proposal import (
    RemediationProposal,
    compile_remediation_proposal,
)


class HoareDebuggingRuntime:
    """Bridge execution telemetry into the diagnostic-only HOARE agent."""

    def __init__(self, agent: HoareDebuggingAgent | None = None) -> None:
        self._agent = agent or HoareDebuggingAgent()

    def diagnose_execution(
        self,
        recorder: ExecutionFeedbackRecorder,
        *,
        execution_id: str,
        session_id: str,
        trusted_evidence: bool | None = None,
        execution_authorized: bool | None = None,
        evidence_refs: tuple[str, ...] = (),
    ) -> DebuggingReport:
        """Diagnose one completed execution using recorder-owned evidence.

        The recorder remains the source of execution truth. Optional trust and
        authorization flags are observations only; this method never promotes
        them into authority and never invokes an executor.
        """
        record = recorder.get(execution_id)
        if record is None:
            raise KeyError(f"Unknown execution_id: {execution_id}")

        observations = _observations(
            record,
            recorder.telemetry_observation(execution_id),
            trusted_evidence=trusted_evidence,
            execution_authorized=execution_authorized,
            evidence_refs=evidence_refs,
        )
        execution_result = _execution_result(record)

        return self._agent.diagnose(
            session_id=session_id,
            execution_id=execution_id,
            observations=observations,
            execution_result=execution_result,
        )

    def propose_remediation_candidate(
        self,
        report: DebuggingReport,
        *,
        proposal_id: str,
        action: str,
        request: PickRequest,
    ) -> RemediationAdmissionCandidate:
        """Create a non-executable candidate for the existing admission gate.

        This is deliberately a two-step operation: diagnosis becomes an
        immutable proposal first, then the proposal is bound to a fresh
        admission request. No authorization or execution occurs here.
        """
        proposal: RemediationProposal = compile_remediation_proposal(
            report=report,
            proposal_id=proposal_id,
            action=action,
        )
        return compile_remediation_admission_candidate(
            proposal=proposal,
            request=request,
        )


def _observations(
    record: PickExecution,
    telemetry: Mapping[str, Any],
    *,
    trusted_evidence: bool | None,
    execution_authorized: bool | None,
    evidence_refs: tuple[str, ...],
) -> dict[str, Any]:
    observations: dict[str, Any] = {
        "execution_id": record.execution_id,
        "tenant_id": record.tenant_id,
        "order_id": record.order_id,
        "requested_sku": record.requested_sku,
        "provider": record.provider,
        "region": record.region,
        "device_id": record.device_id,
        "model": record.model,
        "identity_status": record.identity_status,
        "identity_confidence": record.identity_confidence,
        "telemetry": dict(telemetry),
        "evidence_refs": evidence_refs,
    }
    if trusted_evidence is not None:
        observations["trusted_evidence"] = trusted_evidence
    if execution_authorized is not None:
        observations["execution_authorized"] = execution_authorized
    return observations


def _execution_result(record: PickExecution) -> dict[str, Any]:
    return {
        "status": "SUCCEEDED" if record.success else "FAILED",
        "latency_ms": record.latency_ms,
        "error": record.error,
        "identity_status": record.identity_status,
        "identity_confidence": record.identity_confidence,
    }


__all__ = ["HoareDebuggingRuntime"]
