"""Contract tests for the production HOARE resource authority boundary.

Design/provenance record: 2026-09-10.
"""

from types import SimpleNamespace

import hoare_resource_authority as authority
from hoare_pick_admission import AdmissionDecision


def _context():
    return authority.ResourceAuthorityContext(
        tenant_id="tenant-1",
        order_id="order-1",
        requested_sku="SKU-1",
        device_id="phone-1",
        store_id="store-1",
        aisle="A1",
        shelf="S2",
        source_frame_id="frame-1",
        identity_verified=True,
    )


def test_missing_authority_escalates(monkeypatch):
    monkeypatch.delenv("HOARE_RESOURCE_AUTHORITY_URL", raising=False)
    route = authority.production_resource_route(_context())
    assert route.decision is AdmissionDecision.ESCALATE
    assert route.reason == ["trusted_resource_authority_required"]


def test_http_authority_requires_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("HOARE_RESOURCE_AUTHORITY_URL", "http://hoare.test/route")
    monkeypatch.delenv("HOARE_RESOURCE_AUTHORITY_ALLOW_HTTP", raising=False)
    route = authority.production_resource_route(_context())
    assert route.decision is AdmissionDecision.DENY
    assert route.reason == ["insecure_resource_authority_transport"]


def test_authority_allow_requires_bound_execution_target(monkeypatch):
    monkeypatch.setenv("HOARE_RESOURCE_AUTHORITY_URL", "https://hoare.test/route")

    def fake_post(*_args, **_kwargs):
        return SimpleNamespace(
            status_code=200,
            json=lambda: {"decision": "ALLOW", "provider": "edge", "reason": ["policy_ok"]},
        )

    monkeypatch.setattr(authority.requests, "post", fake_post)
    route = authority.production_resource_route(_context())
    assert route.decision is AdmissionDecision.DENY
    assert route.reason == ["allow_route_requires_provider_and_region"]


def test_authority_allow_returns_normalized_route(monkeypatch):
    monkeypatch.setenv("HOARE_RESOURCE_AUTHORITY_URL", "https://hoare.test/route")
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
                "decision": "allow",
                "provider": "edge",
                "region": "us-east-1",
                "predicted_latency_ms": 14.5,
                "reason": ["latency_ok", "capacity_ok"],
            },
        )

    monkeypatch.setattr(authority.requests, "post", fake_post)
    route = authority.production_resource_route(_context())

    assert route.decision is AdmissionDecision.ALLOW
    assert route.provider == "edge"
    assert route.region == "us-east-1"
    assert route.predicted_latency_ms == 14.5
    assert route.reason == ["latency_ok", "capacity_ok"]
    assert captured["url"] == "https://hoare.test/route"
    assert captured["kwargs"]["json"]["tenant_id"] == "tenant-1"
    assert captured["kwargs"]["json"]["requested_sku"] == "SKU-1"
    assert captured["kwargs"]["json"]["identity_verified"] is True
    assert "resource_route" not in captured["kwargs"]["json"]


def test_authority_unavailable_escalates(monkeypatch):
    monkeypatch.setenv("HOARE_RESOURCE_AUTHORITY_URL", "https://hoare.test/route")

    def fake_post(*_args, **_kwargs):
        raise authority.requests.RequestException("offline")

    monkeypatch.setattr(authority.requests, "post", fake_post)
    route = authority.production_resource_route(_context())
    assert route.decision is AdmissionDecision.ESCALATE
    assert route.reason == ["resource_authority_unavailable"]


def test_authority_unauthorized_denies(monkeypatch):
    monkeypatch.setenv("HOARE_RESOURCE_AUTHORITY_URL", "https://hoare.test/route")

    def fake_post(*_args, **_kwargs):
        return SimpleNamespace(status_code=403)

    monkeypatch.setattr(authority.requests, "post", fake_post)
    route = authority.production_resource_route(_context())
    assert route.decision is AdmissionDecision.DENY
    assert route.reason == ["resource_authority_unauthorized"]


def test_invalid_authority_response_denies(monkeypatch):
    monkeypatch.setenv("HOARE_RESOURCE_AUTHORITY_URL", "https://hoare.test/route")

    def fake_post(*_args, **_kwargs):
        return SimpleNamespace(status_code=200, json=lambda: {"decision": "MAYBE"})

    monkeypatch.setattr(authority.requests, "post", fake_post)
    route = authority.production_resource_route(_context())
    assert route.decision is AdmissionDecision.DENY
    assert route.reason == ["invalid_resource_authority_decision"]
