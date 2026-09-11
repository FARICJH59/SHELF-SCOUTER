"""Conservative product identity verification for pick authorization."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class IdentityStatus(str, Enum):
    OBSERVED = "OBSERVED"
    INFERRED = "INFERRED"
    VERIFIED = "VERIFIED"
    UNKNOWN = "UNKNOWN"


@dataclass
class ProductEvidence:
    source: str
    value: str
    confidence: float


@dataclass
class ProductIdentity:
    requested_sku: str | None
    detected_sku: str | None
    name: str | None
    status: IdentityStatus
    confidence: float
    barcode_match: bool = False
    catalog_match: bool = False
    visual_match: bool = False
    ocr_match: bool = False
    evidence: list[ProductEvidence] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def verify_product(*, requested_sku: str | None = None, detected_sku: str | None = None,
                   name: str | None = None, barcode_match: bool = False,
                   catalog_match: bool = False, visual_match: bool = False,
                   ocr_match: bool = False, evidence: list[ProductEvidence] | None = None) -> ProductIdentity:
    evidence = list(evidence or [])
    if barcode_match and catalog_match and visual_match:
        status, confidence = IdentityStatus.VERIFIED, 0.99
    elif barcode_match and catalog_match:
        status, confidence = IdentityStatus.VERIFIED, 0.97
    elif requested_sku and detected_sku and requested_sku == detected_sku:
        status, confidence = IdentityStatus.VERIFIED, 0.95
    elif visual_match and catalog_match:
        status, confidence = IdentityStatus.VERIFIED, 0.90
    elif visual_match or ocr_match:
        status, confidence = IdentityStatus.INFERRED, 0.70
    elif name:
        status, confidence = IdentityStatus.INFERRED, 0.50
    else:
        status, confidence = IdentityStatus.UNKNOWN, 0.0
    reasons = [f"identity_{status.value.lower()}"]
    return ProductIdentity(requested_sku, detected_sku, name, status, confidence,
                           barcode_match, catalog_match, visual_match, ocr_match,
                           evidence, reasons)


def is_pick_verified(identity: ProductIdentity) -> bool:
    return identity.status is IdentityStatus.VERIFIED and identity.confidence >= 0.90


def identity_summary(identity: ProductIdentity) -> dict:
    return {"status": identity.status.value, "confidence": identity.confidence,
            "requested_sku": identity.requested_sku, "detected_sku": identity.detected_sku,
            "verified": is_pick_verified(identity), "reasons": identity.reasons}
