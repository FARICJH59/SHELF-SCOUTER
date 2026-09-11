"""Server-side resource-route boundary for SHELF-SCOUTER.

Design/provenance record: 2026-09-10.

Production deployments use the configured HOARE resource authority. The
legacy environment-backed route remains only as a development adapter so the
existing tests and local workflow stay intact. The phone never supplies an
authoritative route decision.
"""
from __future__ import annotations

import os

from hoare_pick_admission import AdmissionDecision, ResourceRoute
from hoare_resource_authority import ResourceAuthorityContext, production_resource_route


def server_resource_route() -> ResourceRoute:
    """Return a route from trusted HOARE authority or the dev-only adapter."""
    if os.getenv("HOARE_RESOURCE_AUTHORITY_URL", "").strip():
        return production_resource_route(_request_context())

    return _development_resource_route()


def _request_context() -> ResourceAuthorityContext:
    """Build authority input from trusted server session state plus request data."""
    try:
        from flask import request
        from app import _sessions

        payload = request.get_json(silent=True) or {}
        session_id = str(request.view_args.get("session_id") or "")
        session = _sessions.get(session_id) or {}
        return ResourceAuthorityContext(
            tenant_id=str(session.get("tenant_id") or "default"),
            order_id=str(session.get("order_id") or payload.get("order_id") or "unknown"),
            requested_sku=str(payload.get("sku") or "").strip(),
            device_id=str(session.get("device_id") or "unknown"),
            store_id=session.get("store_id"),
            aisle=payload.get("aisle"),
            shelf=payload.get("shelf"),
            source_frame_id=payload.get("source_frame_id"),
            identity_verified=False,
        )
    except Exception:
        return ResourceAuthorityContext(
            tenant_id="unknown",
            order_id="unknown",
            requested_sku="",
            device_id="unknown",
        )


def _development_resource_route() -> ResourceRoute:
    """Development-only route adapter; default remains fail-closed ESCALATE."""
    raw_decision = os.getenv("HOARE_SERVER_ROUTE_DECISION", "ESCALATE").strip().upper()
    try:
        decision = AdmissionDecision(raw_decision)
    except ValueError:
        return ResourceRoute(
            decision=AdmissionDecision.DENY,
            reason=["invalid_server_resource_route_decision"],
        )

    if decision is AdmissionDecision.ESCALATE:
        return ResourceRoute(
            decision=decision,
            reason=["trusted_resource_authority_required"],
        )

    return ResourceRoute(
        decision=decision,
        provider=os.getenv("HOARE_SERVER_ROUTE_PROVIDER", "edge"),
        region=os.getenv("HOARE_SERVER_ROUTE_REGION", "edge-local"),
        predicted_latency_ms=_float_env("HOARE_SERVER_ROUTE_LATENCY_MS"),
        reason=["server_side_resource_route"],
    )


def _float_env(name: str) -> float | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    try:
        return float(value)
    except ValueError:
        return None
