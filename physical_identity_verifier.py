"""Server-side physical identity verification boundary for SHELF-SCOUTER.

This is intentionally an interface, not a permissive implementation. A real
implementation must derive evidence from the server-controlled frame bytes
(e.g. server-side barcode decoding or an independently validated visual
identity service) and return True only when the physical item is independently
identified as the requested SKU.
"""
from __future__ import annotations

from typing import Protocol


class PhysicalIdentityVerifier(Protocol):
    def verify(self, *, image_bytes: bytes, requested_sku: str, expected_gtin: str | None = None) -> bool:
        """Return True only for independently verified physical identity."""
        ...


class RejectByDefaultPhysicalIdentityVerifier:
    """Fail-closed verifier used until a real server-side verifier is installed."""

    def verify(self, *, image_bytes: bytes, requested_sku: str, expected_gtin: str | None = None) -> bool:
        return False
