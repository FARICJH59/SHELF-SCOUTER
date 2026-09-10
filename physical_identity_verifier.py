"""Server-side physical identity verification boundary for SHELF-SCOUTER.

The phone and vision model are observation sources only. Physical identity is
proved from server-controlled image bytes by an independently executed barcode
decoder and an authorized expected GTIN.

Trust rule:
    image bytes -> independent physical identity -> authorized catalog -> HOARE

A client barcode, model SKU, OCR result, or catalog lookup by itself is never
physical identity proof.
"""
from __future__ import annotations

from io import BytesIO
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
    """Fail-closed verifier used when no production decoder is installed."""

    def verify(self, *, image_bytes: bytes, requested_sku: str, expected_gtin: str | None = None) -> bool:
        return False


class PyzbarBarcodeDecoder:
    """Decode retail barcodes with pyzbar/ZBar from server-controlled bytes.

    pyzbar requires the native ZBar shared library on non-Windows systems.
    The import is intentionally lazy so environments without ZBar remain
    fail-closed instead of turning a missing native dependency into trust.
    """

    _ALLOWED_TYPES = {"EAN13", "EAN8", "UPCA", "UPCE", "I25", "CODE128"}

    def decode(self, image_bytes: bytes) -> list[str]:
        if not image_bytes:
            return []
        try:
            from PIL import Image
            from pyzbar.pyzbar import decode
            with Image.open(BytesIO(image_bytes)) as image:
                image.load()
                decoded = decode(image)
        except Exception:
            return []
        values: list[str] = []
        for item in decoded:
            if str(getattr(item, "type", "")).upper() not in self._ALLOWED_TYPES:
                continue
            try:
                value = item.data.decode("ascii").strip()
            except (AttributeError, UnicodeDecodeError):
                continue
            if value:
                values.append(value)
        return values


class ServerBarcodePhysicalIdentityVerifier:
    """Verify physical identity from a server-side barcode decoder.

    The decoder is injected deliberately for deterministic testing and future
    alternative implementations. Production can use ``PyzbarBarcodeDecoder``
    while isolated environments can continue using the fail-closed verifier.
    The verifier only returns True when a decoded retail barcode exactly
    matches the authorized expected GTIN after strict normalization and
    check-digit validation. SKU authorization remains the responsibility of
    the retailer adapter/evidence authority.
    """

    def __init__(self, decoder: BarcodeDecoder | Callable[[bytes], list[str]]):
        self._decoder = decoder

    def verify(self, *, image_bytes: bytes, requested_sku: str, expected_gtin: str | None = None) -> bool:
        if not image_bytes or not expected_gtin or not requested_sku.strip():
            return False
        expected = _normalize_gtin(expected_gtin)
        if not expected:
            return False
        try:
            raw_values = self._decoder.decode(image_bytes) if hasattr(self._decoder, "decode") else self._decoder(image_bytes)
        except Exception:
            return False
        if not isinstance(raw_values, list):
            return False
        return any(_normalize_gtin(value) == expected for value in raw_values if isinstance(value, str))


def _normalize_gtin(value: str) -> str:
    """Normalize and validate a numeric GTIN-8/12/13/14 value."""
    raw = value.strip()
    if not raw.isdigit() or len(raw) not in {8, 12, 13, 14}:
        return ""
    digits = raw.zfill(14)
    check = sum(
        int(char) * (3 if (len(digits) - 1 - index) % 2 == 0 else 1)
        for index, char in enumerate(digits[:-1])
    )
    if (10 - (check % 10)) % 10 != int(digits[-1]):
        return ""
    return digits
