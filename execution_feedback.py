"""Execution feedback recorder for the SHELF-SCOUTER control loop.

Provenance: 2026-09-13.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import ceil
from time import perf_counter
from uuid import uuid4
from typing import Any, Mapping

from hoare_debugging_agent import DebuggingReport, HoareDebuggingAgent


@dataclass
class PickExecution:
    execution_id: str
    tenant_id: str
    order_id: str
    requested_sku: str
    provider: str
    region: str
    device_id: str
    model: str
    started_at: str
    completed_at: str | None = None
    latency_ms: float | None = None
    success: bool = False
    identity_status: str | None = None
    identity_confidence: float | None = None
    error: str | None = None


class ExecutionFeedbackRecorder:
    """Record execution telemetry and persist diagnostic observations.

    The recorder remains telemetry/diagnostic infrastructure. It does not
    authorize, execute, retry, or mutate the execution boundary.
    """

    _instances: dict[str, "ExecutionFeedbackRecorder"] = {}

    def __init__(self, debugger: HoareDebuggingAgent | None = None) -> None:
        self._records: dict[str, PickExecution] = {}
        self._clocks: dict[str, float] = {}
        self._diagnostic_reports: dict[str, DebuggingReport] = {}
        self._debugger = debugger or HoareDebuggingAgent()

    def start(self, *, tenant_id: str, order_id: str, requested_sku: str,
              provider: str, region: str, device_id: str, model: str) -> PickExecution:
        execution_id = str(uuid4())
        record = PickExecution(
            execution_id, tenant_id, order_id, requested_sku,
            provider, region, device_id, model,
            datetime.now(timezone.utc).isoformat(),
        )
        self._records[execution_id] = record
        self._clocks[execution_id] = perf_counter()
        self._instances[execution_id] = self
        return record

    def complete(self, execution_id: str, *, success: bool,
                 identity_status: str | None = None,
                 identity_confidence: float | None = None,
                 error: str | None = None) -> PickExecution:
        record = self._records[execution_id]
        record.completed_at = datetime.now(timezone.utc).isoformat()
        record.latency_ms = round((perf_counter() - self._clocks.pop(execution_id)) * 1000, 2)
        record.success = success
        record.identity_status = identity_status
        record.identity_confidence = identity_confidence
        record.error = error

        # Diagnostic-only post-completion hook. The existing execution path is
        # already complete at this point; diagnosis cannot change its result.
        self._diagnostic_reports[execution_id] = self._debugger.diagnose(
            session_id="execution-feedback",
            execution_id=execution_id,
            observations={
                "tenant_id": record.tenant_id,
                "order_id": record.order_id,
                "requested_sku": record.requested_sku,
                "provider": record.provider,
                "region": record.region,
                "device_id": record.device_id,
                "model": record.model,
                "identity_status": record.identity_status,
                "identity_confidence": record.identity_confidence,
                "evidence_refs": (f"execution:{execution_id}",),
                "telemetry": self.telemetry_observation(execution_id),
            },
            execution_result={
                "status": "SUCCEEDED" if success else "FAILED",
                "latency_ms": record.latency_ms,
                "error": record.error,
                "identity_status": record.identity_status,
                "identity_confidence": record.identity_confidence,
            },
        )
        return record

    def get(self, execution_id: str) -> PickExecution | None:
        return self._records.get(execution_id)

    def diagnostic_report(self, execution_id: str) -> DebuggingReport | None:
        """Return the internal diagnostic report for control-plane telemetry."""
        return self._diagnostic_reports.get(execution_id)

    def diagnostic_snapshot(self) -> list[DebuggingReport]:
        """Return diagnostic reports without exposing them through pick APIs."""
        return list(self._diagnostic_reports.values())

    @classmethod
    def attach_execution_boundary(
        cls,
        execution_id: str,
        trace: Mapping[str, Any],
    ) -> None:
        """Attach signed-boundary provenance to an existing diagnostic report.

        This is a control-plane telemetry hook only. It never changes the
        PickExecution result and never grants authority to the debugger.
        """
        recorder = cls._instances.get(execution_id)
        if recorder is None:
            return
        report = recorder._diagnostic_reports.get(execution_id)
        if report is None:
            return

        metadata = dict(report.metadata)
        metadata["execution_boundary"] = dict(trace)
        recorder._diagnostic_reports[execution_id] = DebuggingReport(
            schema=report.schema,
            debugger_version=report.debugger_version,
            session_id=report.session_id,
            execution_id=report.execution_id,
            disposition=report.disposition,
            findings=report.findings,
            metadata=metadata,
        )

    def snapshot(self) -> list[PickExecution]:
        return list(self._records.values())

    def _p95_latency(self, record: PickExecution) -> float | None:
        values = sorted(
            item.latency_ms
            for item in self._records.values()
            if item.completed_at
            and item.latency_ms is not None
            and item.provider == record.provider
            and item.region == record.region
            and item.model == record.model
        )
        if not values:
            return None
        # Nearest-rank P95: rank = ceil(0.95 * N), with a minimum rank of 1.
        rank = max(1, ceil(0.95 * len(values)))
        return values[rank - 1]

    def telemetry_observation(self, execution_id: str) -> dict:
        record = self._records[execution_id]
        return {
            "source": "shelf-scouter-execution",
            "region": record.region,
            "observedAt": record.completed_at,
            "latencyMs": record.latency_ms,
            "latencyP95Ms": self._p95_latency(record),
            "modelAvailability": record.success,
            "confidence": record.identity_confidence,
            "provider": record.provider,
            "model": record.model,
        }
