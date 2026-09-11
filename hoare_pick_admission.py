"""Provider-neutral admission contract for SHELF-SCOUTER picks."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from product_verification import IdentityStatus, ProductIdentity, is_pick_verified


class AdmissionDecision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    ESCALATE = "ESCALATE"


@dataclass
class PickRequest:
    tenant_id: str
    order_id: str
    requested_sku: str
    device_id: str
    store_id: str | None = None
    aisle: str | None = None
    shelf: str | None = None
    intent: str = "customer_order_pick"


@dataclass
class ResourceRoute:
    decision: AdmissionDecision
    provider: str | None = None
    region: str | None = None
    predicted_latency_ms: float | None = None
    reason: list[str] | None = None


@dataclass
class PickAdmission:
    decision: AdmissionDecision
    reasons: list[str]
    request: PickRequest
    identity_status: IdentityStatus
    identity_confidence: float
    resource_route: ResourceRoute | None = None


def admit_pick(request: PickRequest, identity: ProductIdentity,
               resource_route: ResourceRoute | None = None,
               require_verified_identity: bool = True) -> PickAdmission:
    reasons: list[str] = []
    if request.requested_sku and identity.detected_sku and request.requested_sku != identity.detected_sku:
        return PickAdmission(AdmissionDecision.DENY, ["requested_sku_detected_sku_mismatch"],
                             request, identity.status, identity.confidence, resource_route)
    if require_verified_identity and not is_pick_verified(identity):
        return PickAdmission(AdmissionDecision.ESCALATE, ["product_identity_not_verified"],
                             request, identity.status, identity.confidence, resource_route)
    if resource_route:
        if resource_route.decision is AdmissionDecision.DENY:
            return PickAdmission(AdmissionDecision.DENY, resource_route.reason or ["resource_route_denied"],
                                 request, identity.status, identity.confidence, resource_route)
        if resource_route.decision is AdmissionDecision.ESCALATE:
            return PickAdmission(AdmissionDecision.ESCALATE, resource_route.reason or ["resource_route_escalated"],
                                 request, identity.status, identity.confidence, resource_route)
    reasons.extend(["product_identity_verified", "resource_route_accepted"])
    return PickAdmission(AdmissionDecision.ALLOW, reasons, request, identity.status, identity.confidence, resource_route)
