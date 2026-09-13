"""HOARE debugging agent.

Provenance: 2026-09-13.

This module is intentionally diagnostic-only. It can observe execution evidence,
classify failures, and propose remediation. It cannot authorize or execute a
remediation. Any proposed action must be passed back through the normal HOARE /
AEGIS admission and signed execution boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


SCHEMA_VERSION = "hoare.debugging-report.v1"
DEBUGGER_VERSION = "1.0.0"


class DiagnosticSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class DiagnosticDisposition(str, Enum):
    HEALTHY = "HEALTHY"
    INVESTIGATE = "INVESTIGATE"
    ESCALATE = "ESCALATE"


@dataclass(frozen=True)
class DiagnosticFinding:
    code: str
    severity: DiagnosticSeverity
    message: str
    evidence_refs: tuple[str, ...] = ()
    proposed_actions: tuple[str, ...] = ()


@dataclass(frozen=True)
class DebuggingReport:
    schema: str
    debugger_version: str
    session_id: str
    execution_id: str | None
    disposition: DiagnosticDisposition
    findings: tuple[DiagnosticFinding, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


class HoareDebuggingAgent:
    """Observe and diagnose; never authorize or execute."""

    def diagnose(
        self,
        *,
        session_id: str,
        execution_id: str | None = None,
        observations: Mapping[str, Any] | None = None,
        execution_result: Mapping[str, Any] | None = None,
    ) -> DebuggingReport:
        observations = observations or {}
        execution_result = execution_result or {}
        findings: list[DiagnosticFinding] = []

        status = str(execution_result.get("status", "")).upper()
        error = execution_result.get("error")
        latency_ms = execution_result.get("latency_ms")

        if status in {"FAILED", "ERROR"} or error:
            findings.append(
                DiagnosticFinding(
                    code="EXECUTION_FAILURE",
                    severity=DiagnosticSeverity.ERROR,
                    message=str(error or "Execution reported failure."),
                    evidence_refs=_refs(observations),
                    proposed_actions=("inspect_execution_telemetry", "revalidate_inputs"),
                )
            )

        if isinstance(latency_ms, (int, float)) and latency_ms > 5000:
            findings.append(
                DiagnosticFinding(
                    code="LATENCY_HIGH",
                    severity=DiagnosticSeverity.WARNING,
                    message=f"Execution latency is {latency_ms} ms.",
                    evidence_refs=_refs(observations),
                    proposed_actions=("inspect_latency_breakdown",),
                )
            )

        if observations.get("trusted_evidence") is False:
            findings.append(
                DiagnosticFinding(
                    code="TRUST_BOUNDARY_MISSING",
                    severity=DiagnosticSeverity.CRITICAL,
                    message="Trusted evidence was not established; diagnosis cannot promote client data to authority.",
                    evidence_refs=_refs(observations),
                    proposed_actions=("reverify_server_authority", "escalate_to_operator"),
                )
            )

        if observations.get("execution_authorized") is False:
            findings.append(
                DiagnosticFinding(
                    code="EXECUTION_NOT_AUTHORIZED",
                    severity=DiagnosticSeverity.CRITICAL,
                    message="Execution authorization was not established.",
                    evidence_refs=_refs(observations),
                    proposed_actions=("recheck_admission_and_signed_request", "escalate_to_operator"),
                )
            )

        if not findings:
            disposition = DiagnosticDisposition.HEALTHY
        elif any(f.severity == DiagnosticSeverity.CRITICAL for f in findings):
            disposition = DiagnosticDisposition.ESCALATE
        else:
            disposition = DiagnosticDisposition.INVESTIGATE

        return DebuggingReport(
            schema=SCHEMA_VERSION,
            debugger_version=DEBUGGER_VERSION,
            session_id=session_id,
            execution_id=execution_id,
            disposition=disposition,
            findings=tuple(findings),
            metadata={"authority": "diagnostic-only", "can_execute": False},
        )


def _refs(observations: Mapping[str, Any]) -> tuple[str, ...]:
    refs = observations.get("evidence_refs", ())
    if isinstance(refs, str):
        return (refs,)
    if isinstance(refs, (list, tuple)):
        return tuple(str(item) for item in refs if str(item).strip())
    return ()


__all__ = [
    "DEBUGGER_VERSION",
    "SCHEMA_VERSION",
    "DiagnosticDisposition",
    "DiagnosticFinding",
    "DiagnosticSeverity",
    "DebuggingReport",
    "HoareDebuggingAgent",
]
