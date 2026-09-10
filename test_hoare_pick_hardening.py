from execution_feedback import ExecutionFeedbackRecorder
from hoare_resource_route import server_resource_route
from hoare_pick_admission import AdmissionDecision


def test_server_route_defaults_to_escalate(monkeypatch):
    monkeypatch.delenv("HOARE_SERVER_ROUTE_DECISION", raising=False)
    route = server_resource_route()
    assert route.decision is AdmissionDecision.ESCALATE
    assert route.reason == ["trusted_resource_authority_required"]


def test_server_route_allow_is_server_side(monkeypatch):
    monkeypatch.setenv("HOARE_SERVER_ROUTE_DECISION", "ALLOW")
    monkeypatch.setenv("HOARE_SERVER_ROUTE_PROVIDER", "edge")
    monkeypatch.setenv("HOARE_SERVER_ROUTE_REGION", "edge-local")
    monkeypatch.setenv("HOARE_SERVER_ROUTE_LATENCY_MS", "12.5")
    route = server_resource_route()
    assert route.decision is AdmissionDecision.ALLOW
    assert route.provider == "edge"
    assert route.region == "edge-local"
    assert route.predicted_latency_ms == 12.5


def test_server_route_invalid_decision_denies(monkeypatch):
    monkeypatch.setenv("HOARE_SERVER_ROUTE_DECISION", "not-a-decision")
    route = server_resource_route()
    assert route.decision is AdmissionDecision.DENY
    assert route.reason == ["invalid_server_resource_route_decision"]


def test_latency_p95_is_aggregate(monkeypatch):
    recorder = ExecutionFeedbackRecorder()
    executions = []
    for _ in range(20):
        execution = recorder.start(
            tenant_id="tenant", order_id="order", requested_sku="SKU-1",
            provider="edge", region="edge-local", device_id="phone", model="vision",
        )
        recorder._clocks[execution.execution_id] = 0.0
        monkeypatch.setattr("execution_feedback.perf_counter", lambda: 0.001)
        executions.append(recorder.complete(execution.execution_id, success=True))

    # Make the completed records deterministic and non-identical. The nearest-rank
    # P95 of 1..20 is 20, proving telemetry is not copied from the selected record.
    for index, execution in enumerate(executions, start=1):
        execution.latency_ms = float(index)

    observation = recorder.telemetry_observation(executions[-1].execution_id)
    assert observation["latencyMs"] == 20.0
    assert observation["latencyP95Ms"] == 20.0
