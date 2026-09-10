"""Server-side trusted product evidence for HOARE pick admission.

Client-supplied vision/barcode fields are observations only. This module creates
signed evidence only after a trusted server-side verification path has compared
those observations with an authorized retailer adapter.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import asdict, dataclass

from retailer_adapters import RetailerAdapter


@dataclass(frozen=True)
class TrustedProductEvidence:
    session_id: str
    frame_id: str
    requested_sku: str
    detected_sku: str | None
    barcode_match: bool
    catalog_match: bool
    visual_match: bool
    ocr_match: bool
    issuer: str
    issued_at: int
    expires_at: int
    signature: str


class TrustedEvidenceAuthority:
    """Issue and verify tamper-evident evidence on the server side."""

    def __init__(self, secret: str | bytes | None = None, *, issuer: str = "shelf-scouter-trusted-evidence", ttl_seconds: int = 300):
        raw = secret if secret is not None else os.getenv("HOARE_TRUSTED_EVIDENCE_SECRET")
        self._secret = raw.encode("utf-8") if isinstance(raw, str) else raw
        self.issuer = issuer
        self.ttl_seconds = ttl_seconds

    @property
    def configured(self) -> bool:
        return bool(self._secret)

    def _canonical(self, payload: dict) -> bytes:
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def _sign(self, payload: dict) -> str:
        if not self._secret:
            raise RuntimeError("HOARE_TRUSTED_EVIDENCE_SECRET is not configured")
        digest = hmac.new(self._secret, self._canonical(payload), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    def issue(self, *, session_id: str, frame_id: str, requested_sku: str,
              detected_sku: str | None, barcode_match: bool, catalog_match: bool,
              visual_match: bool = False, ocr_match: bool = False,
              now: int | None = None) -> TrustedProductEvidence:
        issued = int(time.time() if now is None else now)
        payload = {
            "session_id": session_id, "frame_id": frame_id,
            "requested_sku": requested_sku, "detected_sku": detected_sku,
            "barcode_match": bool(barcode_match), "catalog_match": bool(catalog_match),
            "visual_match": bool(visual_match), "ocr_match": bool(ocr_match),
            "issuer": self.issuer, "issued_at": issued,
            "expires_at": issued + self.ttl_seconds,
        }
        return TrustedProductEvidence(**payload, signature=self._sign(payload))

    def verify(self, evidence: TrustedProductEvidence, *, now: int | None = None) -> bool:
        if not self._secret:
            return False
        current = int(time.time() if now is None else now)
        if evidence.issuer != self.issuer or current > evidence.expires_at or evidence.expires_at < evidence.issued_at:
            return False
        payload = asdict(evidence)
        signature = payload.pop("signature")
        return hmac.compare_digest(signature, self._sign(payload))


def verify_against_adapter(*, authority: TrustedEvidenceAuthority, adapter: RetailerAdapter,
                           session_id: str, frame_id: str, requested_sku: str,
                           detected_sku: str | None, barcode: str | None,
                           store_id: str | None = None) -> TrustedProductEvidence | None:
    """Issue evidence only when an authorized adapter establishes a match."""
    if not authority.configured:
        return None
    query = detected_sku or requested_sku
    items = adapter.resolve_item(query=query, store_id=store_id, barcode=barcode)
    catalog_match = any(item.sku and item.sku == requested_sku for item in items)
    barcode_match = bool(barcode) and any(item.gtin and item.gtin == barcode for item in items)
    if not catalog_match and not barcode_match:
        return None
    matched = next((item for item in items if item.sku == requested_sku or (barcode and item.gtin == barcode)), None)
    return authority.issue(
        session_id=session_id, frame_id=frame_id, requested_sku=requested_sku,
        detected_sku=matched.sku if matched else detected_sku,
        barcode_match=barcode_match, catalog_match=catalog_match,
    )
