"""Retailer-neutral adapter boundary for SHELF-SCOUTER.

The phone and vision layers never contain retailer credentials. Enterprise
connectors implement this interface after the retailer authorizes access.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class RetailItem:
    retailer: str
    store_id: str | None
    sku: str | None
    gtin: str | None
    name: str
    available: bool | None = None
    quantity: int | None = None
    metadata: dict[str, Any] | None = None


class RetailerAdapter(ABC):
    name = "generic"

    @abstractmethod
    def resolve_item(self, *, query: str, store_id: str | None = None, barcode: str | None = None) -> list[RetailItem]:
        """Resolve an order item into retailer-specific identifiers."""
        raise NotImplementedError

    def verify_availability(self, item: RetailItem) -> RetailItem:
        """Optional availability check; default leaves the item unchanged."""
        return item


class CatalogOnlyAdapter(RetailerAdapter):
    """Safe local adapter used until an authorized retailer API is connected."""

    name = "catalog-only"

    def __init__(self, catalog: list[dict[str, Any]] | None = None):
        self.catalog = catalog or []

    def resolve_item(self, *, query: str, store_id: str | None = None, barcode: str | None = None) -> list[RetailItem]:
        q = query.strip().lower()
        candidates = []
        for row in self.catalog:
            text = " ".join(str(row.get(k, "")) for k in ("name", "sku", "gtin", "brand", "label_text")).lower()
            if (barcode and barcode in text) or (q and q in text):
                candidates.append(RetailItem(
                    retailer=str(row.get("retailer", "catalog")),
                    store_id=store_id,
                    sku=row.get("sku"),
                    gtin=row.get("gtin"),
                    name=str(row.get("name", "")),
                    available=row.get("available"),
                    quantity=row.get("quantity"),
                    metadata=row,
                ))
        return candidates


ADAPTERS: dict[str, RetailerAdapter] = {"catalog": CatalogOnlyAdapter()}


def get_adapter(retailer: str | None) -> RetailerAdapter:
    return ADAPTERS.get((retailer or "catalog").lower(), ADAPTERS["catalog"])
