"""Execution telemetry to HOARE diagnostics integration tests.

Provenance: 2026-09-13.
"""

from execution_feedback import ExecutionFeedbackRecorder
from hoare_debugging_agent import DiagnosticDisposition


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
