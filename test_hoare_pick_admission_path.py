"""Executable-path tests for the HOARE pick admission boundary.

Design/provenance record: 2026-09-10.
These tests verify that trusted evidence and the server-side resource decision
both gate the existing /pick execution path.
"""
from dataclasses import asdict
import time

import mobile_gateway
from trusted_product_evidence import TrustedEvidenceAuthority


SKU = "SKU-1"
SESSION_ID = "admission-test-session"
FRAME_ID = "admission-test-frame"


def _install_frame(authority: TrustedEvidenceAuthority):
    evidence = authority.issue(
        session_id=SESSION_ID,
        frame_id=FRAME_ID,
        requested_sku=SKU,
        detected_sku=SKU,
        barcode_match=True,
        catalog_match=True,
        visual_match=True,
        now=int(time.time()),
    )
    mobile_gateway._sessions[SESSION_ID] = {
        "session_id": SESSION_ID,
        "tenant_id": "tenant-test",
        "order_id": "order-test",
        "device_id": "phone-test",
        "retailer": "catalog",
        "store_id": "store-test",
        "frames": [{
            "frame_id": FRAME_ID,
            "session_id": SESSION_ID,
            "pick_match": {"candidate": {"sku": SKU, "name": "Test Item"}},
            "trusted_evidence": asdict(evidence),
            "result": {"model": "targeted-vision"},
        }],
        "picks": [],
    }


def _authority_swap(monkeypatch):
    authority = TrustedEvidenceAuthority("admission-test-secret", ttl_seconds=300)
    monkeypatch.setattr(mobile_gateway, "_EVIDENCE_AUTHORITY", authority)
    _install_frame(authority)
    return authority


def test_forged_trusted_evidence_cannot_reach_execution(monkeypatch):
    _authority_swap(monkeypatch)
    frame = mobile_gateway._sessions[SESSION_ID]["frames"][0]
    forged = dict(frame["trusted_evidence"])
    forged["detected_sku"] = "EVIL-SKU"
    frame["trusted_evidence"] = forged

    monkeypatch.setenv("HOARE_SERVER_ROUTE_DECISION", "ALLOW")

    def execution_must_not_start(**_kwargs):
        raise AssertionError("execution reached with forged trusted evidence")

    monkeypatch.setattr(mobile_gateway._feedback, "start", execution_must_not_start)
    client = mobile_gateway.app.test_client()
    response = client.post(
        f"/v1/sessions/{SESSION_ID}/pick",
        json={
            "product": "Test Item",
            "quantity": 1,
            "source_frame_id": FRAME_ID,
            "sku": SKU,
            "resource_route": {"decision": "ALLOW", "provider": "attacker"},
        },
    )

    assert response.status_code == 409
    assert response.get_json()["status"] == "ESCALATE"
    assert mobile_gateway._sessions[SESSION_ID]["picks"] == []
    assert mobile_gateway._trusted_evidence_from_frame(frame) is None


def test_client_allow_route_cannot_override_server_escalate(monkeypatch):
    _authority_swap(monkeypatch)
    monkeypatch.setenv("HOARE_SERVER_ROUTE_DECISION", "ESCALATE")

    started = False

    def execution_must_not_start(**_kwargs):
        nonlocal started
        started = True
        raise AssertionError("execution reached with server-side ESCALATE")

    monkeypatch.setattr(mobile_gateway._feedback, "start", execution_must_not_start)
    client = mobile_gateway.app.test_client()
    response = client.post(
        f"/v1/sessions/{SESSION_ID}/pick",
        json={
            "product": "Test Item",
            "quantity": 1,
            "source_frame_id": FRAME_ID,
            "sku": SKU,
            "resource_route": {"decision": "ALLOW", "provider": "attacker"},
        },
    )

    body = response.get_json()
    assert response.status_code == 409
    assert body["status"] == "ESCALATE"
    assert body["resource_route"]["decision"] == "ESCALATE"
    assert started is False
    assert mobile_gateway._sessions[SESSION_ID]["picks"] == []


def test_valid_server_evidence_and_server_allow_reach_existing_execution_path(monkeypatch):
    _authority_swap(monkeypatch)
    monkeypatch.setenv("HOARE_SERVER_ROUTE_DECISION", "ALLOW")
    monkeypatch.setenv("HOARE_SERVER_ROUTE_PROVIDER", "edge")
    monkeypatch.setenv("HOARE_SERVER_ROUTE_REGION", "edge-local")

    client = mobile_gateway.app.test_client()
    response = client.post(
        f"/v1/sessions/{SESSION_ID}/pick",
        json={
            "product": "Test Item",
            "quantity": 1,
            "source_frame_id": FRAME_ID,
            "sku": SKU,
            "resource_route": {"decision": "DENY", "provider": "attacker"},
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "confirmed"
    assert body["admission"]["decision"] == "ALLOW"
    assert body["resource_route"]["decision"] == "ALLOW"
    assert body["execution"]["source"] == "shelf-scouter-execution"
    assert len(mobile_gateway._sessions[SESSION_ID]["picks"]) == 1

def test_model_only_sku_match_cannot_create_trusted_identity():
    """A model SKU match without trusted evidence must remain unverified."""
    from mobile_gateway import _identity_from_frame
    from product_verification import IdentityStatus

    frame = {
        "session_id": "security-test-session",
        "frame_id": "security-test-frame",
        "pick_match": {
            "found": True,
            "candidate": {
                "sku": "SKU-1",
                "name": "Model Suggested Product",
            },
        },
        "physical_identity_verified": False,
        "physical_identity_gtin": None,
    }

    identity = _identity_from_frame(frame, "SKU-1")

    assert identity.status is not IdentityStatus.VERIFIED
    assert identity.detected_sku is None
    assert identity.confidence < 0.90
