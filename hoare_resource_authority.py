"""Provider-neutral client for the trusted HOARE resource authority.

Design/provenance record: 2026-09-10.

This module is the production boundary between SHELF-SCOUTER and HOARE's
resource-routing authority. The phone/client never controls this request.
Production mode is enabled by HOARE_RESOURCE_AUTHORITY_URL and fails closed
when the authority cannot be reached or returns an invalid decision.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlparse

import requests

from hoare_pick_admission import AdmissionDecision, ResourceRoute


@dataclass(frozen=True)
class ResourceAuthorityContext:
    """Trusted server-side context sent to the HOARE resource authority."""

    tenant_id: str
    order_id: str
    requested_sku: str
    device_id: str
    store_id: str | None = None
    aisle: str | None = None
    shelf: str | None = None
    source_frame_id: str | None = None
    identity_verified: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "order_id": self.order_id,
            "requested_sku": self.requested_sku,
            "device_id": self.device_id,
            "store_id": self.store_id,
            "aisle": self.aisle,
            "shelf": self.shelf,
            "source_frame_id": self.source_frame_id,
            "identity_verified": self.identity_verified,
            "intent": "customer_order_pick",
        }


def production_resource_route(context: ResourceAuthorityContext) -> ResourceRoute:
    """Ask the configured HOARE authority for a resource route.

    Any transport, configuration, schema, or authorization failure escalates.
    An invalid explicit decision is denied. ALLOW requires provider and region
    so an authority cannot accidentally authorize an unbound execution target.
    """
    url = os.getenv("HOARE_RESOURCE_AUTHORITY_URL", "").strip()
    if not url:
        return ResourceRoute(
            decision=AdmissionDecision.ESCALATE,
            reason=["trusted_resource_authority_required"],
        )

    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        return ResourceRoute(
            decision=AdmissionDecision.DENY,
            reason=["invalid_resource_authority_url"],
        )
    if parsed.scheme == "http" and os.getenv("HOARE_RESOURCE_AUTHORITY_ALLOW_HTTP", "false").strip().lower() != "true":
        return ResourceRoute(
            decision=AdmissionDecision.DENY,
            reason=["insecure_resource_authority_transport"],
        )

    try:
        timeout = float(os.getenv("HOARE_RESOURCE_AUTHORITY_TIMEOUT_SECONDS", "2.0"))
    except ValueError:
        return ResourceRoute(
            decision=AdmissionDecision.DENY,
            reason=["invalid_resource_authority_timeout"],
        )
    if timeout <= 0 or timeout > 10:
        return ResourceRoute(
            decision=AdmissionDecision.DENY,
            reason=["invalid_resource_authority_timeout"],
        )

    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    token = os.getenv("HOARE_RESOURCE_AUTHORITY_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = requests.post(
            url,
            json=context.to_payload(),
            headers=headers,
            timeout=timeout,
        )
        if response.status_code in {401, 403}:
            return ResourceRoute(
                decision=AdmissionDecision.DENY,
                reason=["resource_authority_unauthorized"],
            )
        if response.status_code < 200 or response.status_code >= 300:
            return ResourceRoute(
                decision=AdmissionDecision.ESCALATE,
                reason=["resource_authority_unavailable"],
            )
        body = response.json()
    except (requests.RequestException, ValueError):
        return ResourceRoute(
            decision=AdmissionDecision.ESCALATE,
            reason=["resource_authority_unavailable"],
        )

    return _route_from_authority_response(body)


def _route_from_authority_response(body: Any) -> ResourceRoute:
    if not isinstance(body, Mapping):
        return ResourceRoute(
            decision=AdmissionDecision.DENY,
            reason=["invalid_resource_authority_response"],
        )

    raw_decision = body.get("decision")
    try:
        decision = AdmissionDecision(str(raw_decision).strip().upper())
    except ValueError:
        return ResourceRoute(
            decision=AdmissionDecision.DENY,
            reason=["invalid_resource_authority_decision"],
        )

    reason = body.get("reason", [])
    if isinstance(reason, str):
        reason = [reason]
    if not isinstance(reason, list) or not all(isinstance(item, str) for item in reason):
        return ResourceRoute(
            decision=AdmissionDecision.DENY,
            reason=["invalid_resource_authority_reason"],
        )

    provider = body.get("provider")
    region = body.get("region")
    if provider is not None and not isinstance(provider, str):
        return ResourceRoute(decision=AdmissionDecision.DENY, reason=["invalid_resource_authority_provider"])
    if region is not None and not isinstance(region, str):
        return ResourceRoute(decision=AdmissionDecision.DENY, reason=["invalid_resource_authority_region"])

    if decision is AdmissionDecision.ALLOW and (not provider or not region):
        return ResourceRoute(
            decision=AdmissionDecision.DENY,
            reason=["allow_route_requires_provider_and_region"],
        )

    latency = body.get("predicted_latency_ms")
    if latency is not None:
        try:
            latency = float(latency)
        except (TypeError, ValueError):
            return ResourceRoute(
                decision=AdmissionDecision.DENY,
                reason=["invalid_resource_authority_latency"],
            )
        if latency < 0:
            return ResourceRoute(
                decision=AdmissionDecision.DENY,
                reason=["invalid_resource_authority_latency"],
            )

    return ResourceRoute(
        decision=decision,
        provider=provider,
        region=region,
        predicted_latency_ms=latency,
        reason=reason or ["hoare_resource_authority"],
    )
