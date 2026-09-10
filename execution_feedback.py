"""Execution feedback recorder for the SHELF-SCOUTER control loop."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import ceil
from time import perf_counter
from uuid import uuid4


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
    def __init__(self) -> None:
        self._records: dict[str, PickExecution] = {}
        self._clocks: dict[str, float] = {}

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
        return record

    def get(self, execution_id: str) -> PickExecution | None:
        return self._records.get(execution_id)

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
