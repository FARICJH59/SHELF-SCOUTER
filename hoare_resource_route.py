"""Server-side resource-route boundary for SHELF-SCOUTER.

The phone never supplies an authoritative route. Production deployments should
replace this small adapter with the Tech Fusion/HOARE resource-routing client.
The default is ESCALATE so missing configuration cannot silently authorize work.
"""
from __future__ import annotations

import os

from hoare_pick_admission import AdmissionDecision, ResourceRoute


def server_resource_route() -> ResourceRoute:
    """Return a route decision configured on the trusted server side."""
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
