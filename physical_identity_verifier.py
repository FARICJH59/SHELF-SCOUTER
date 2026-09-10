"""Server-side physical identity verification boundary for SHELF-SCOUTER.

The phone and vision model are observation sources only. This module provides
an injectable server-side barcode/physical-identity verifier without shipping
a permissive fallback. A deployment must supply a real decoder/verifier that
operates on server-controlled image bytes.

Trust rule:
    image bytes -> independent physical identity -> authorized catalog -> HOARE

A client barcode, model SKU, OCR result, or catalog lookup by itself is never
physical identity proof.
"""
from __future__ import annotations

from typing import Callable, Protocol


class PhysicalIdentityVerifier(Protocol):
    def verify(self, *, image_bytes: bytes, requested_sku: str, expected_gtin: str | None = None) -> bool:
        """Return True only for independently verified physical identity."""
        ...


class BarcodeDecoder(Protocol):
    def decode(self, image_bytes: bytes) -> list[str]:
        """Return barcodes decoded directly from server-controlled image bytes."""
        ...


class RejectByDefaultPhysicalIdentityVerifier:
    """Fail-closed verifier used until a real server-side verifier is installed."""

    def verify(self, *, image_bytes: bytes, requested_sku: str, expected_gtin: str | None = None) -> bool:
        return False


class ServerBarcodePhysicalIdentityVerifier:
    """Verify physical identity from a server-side barcode decoder.

    The decoder is injected deliberately: this boundary does not pretend that
    an unavailable barcode library can prove identity. A deployment can supply
    a production decoder such as a native barcode service/library. The verifier
    only returns True when a decoded barcode exactly matches the authorized
    expected GTIN. SKU authorization remains the responsibility of the retailer
    adapter/evidence authority.
    """

    def __init__(self, decoder: BarcodeDecoder | Callable[[bytes], list[str]]):
        self._decoder = decoder

    def verify(self, *, image_bytes: bytes, requested_sku: str, expected_gtin: str | None = None) -> bool:
        if not image_bytes or not expected_gtin:
            return False
        try:
            raw_values = self._decoder.decode(image_bytes) if hasattr(self._decoder, "decode") else self._decoder(image_bytes)
        except Exception:
            return False
        if not isinstance(raw_values, list):
            return False
        expected = _normalize_gtin(expected_gtin)
        if not expected:
            return False
        return any(_normalize_gtin(value) == expected for value in raw_values if isinstance(value, str))


def _normalize_gtin(value: str) -> str:
    """Normalize numeric GTIN observations without accepting arbitrary text."""
    digits = "".join(ch for ch in value.strip() if ch.isdigit())
    if not digits or len(digits) not in {8, 12, 13, 14}:
        return ""
    return digits.zfill(14)
