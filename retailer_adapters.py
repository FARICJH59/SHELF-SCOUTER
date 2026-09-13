"""Retailer-neutral adapter boundary for SHELF-SCOUTER.

The phone and vision layers never contain retailer credentials. Enterprise
connectors implement this interface after the retailer authorizes access.

Security boundary:
- resolve_item() is general product resolution.
- resolve_gtin() is physical barcode -> authorized catalog identity.
- A barcode observation is not trusted merely because it is client supplied.
- Production physical identity must come from the server-side decoder or
  another independently trusted evidence source before HOARE admission.
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


def normalize_gtin(value: str | None) -> str:
    """Normalize a numeric GTIN-8/12/13/14 value.

    Returns the canonical 14-digit representation only when the GS1
    check digit is valid. Invalid values return an empty string.
    """
    if value is None:
        return ""

    raw = str(value).strip()

    if not raw.isdigit() or len(raw) not in {8, 12, 13, 14}:
        return ""

    digits = raw.zfill(14)

    check = sum(
        int(char) * (3 if (len(digits) - 2 - index) % 2 == 0 else 1)
        for index, char in enumerate(digits[:-1])
    )

    expected = (10 - (check % 10)) % 10

    if expected != int(digits[-1]):
        return ""

    return digits


class RetailerAdapter(ABC):
    name = "generic"

    @abstractmethod
    def resolve_item(
        self,
        *,
        query: str,
        store_id: str | None = None,
        barcode: str | None = None,
    ) -> list[RetailItem]:
        """Resolve an order item into retailer-specific identifiers."""
        raise NotImplementedError

    def resolve_gtin(
        self,
        *,
        gtin: str,
        store_id: str | None = None,
    ) -> list[RetailItem]:
        """Resolve a server-observed GTIN to authorized catalog items.

        This is intentionally separate from resolve_item(). Implementations
        must perform exact normalized GTIN matching and must not treat a
        client-provided barcode string as proof of physical identity.
        """
        normalized = normalize_gtin(gtin)

        if not normalized:
            return []

        return [
            item
            for item in self.resolve_item(
                query=normalized,
                store_id=store_id,
                barcode=normalized,
            )
            if normalize_gtin(item.gtin) == normalized
        ]

    def verify_availability(self, item: RetailItem) -> RetailItem:
        """Optional availability check; default leaves the item unchanged."""
        return item


class CatalogOnlyAdapter(RetailerAdapter):
    """Safe local adapter used until an authorized retailer API is connected."""

    name = "catalog-only"

    def __init__(self, catalog: list[dict[str, Any]] | None = None):
        self.catalog = catalog or []

    def resolve_item(
        self,
        *,
        query: str,
        store_id: str | None = None,
        barcode: str | None = None,
    ) -> list[RetailItem]:
        q = query.strip().lower()

        candidates = []

        for row in self.catalog:
            text = " ".join(
                str(row.get(k, ""))
                for k in ("name", "sku", "gtin", "brand", "label_text")
            ).lower()

            if (barcode and barcode in text) or (q and q in text):
                candidates.append(
                    RetailItem(
                        retailer=str(row.get("retailer", "catalog")),
                        store_id=store_id,
                        sku=row.get("sku"),
                        gtin=row.get("gtin"),
                        name=str(row.get("name", "")),
                        available=row.get("available"),
                        quantity=row.get("quantity"),
                        metadata=row,
                    )
                )

        return candidates

    def resolve_gtin(
        self,
        *,
        gtin: str,
        store_id: str | None = None,
    ) -> list[RetailItem]:
        """Exact GTIN lookup for server-derived barcode evidence."""
        normalized = normalize_gtin(gtin)

        if not normalized:
            return []

        matches = []

        for row in self.catalog:
            row_gtin = normalize_gtin(row.get("gtin"))

            if row_gtin != normalized:
                continue

            matches.append(
                RetailItem(
                    retailer=str(row.get("retailer", "catalog")),
                    store_id=store_id,
                    sku=row.get("sku"),
                    gtin=row.get("gtin"),
                    name=str(row.get("name", "")),
                    available=row.get("available"),
                    quantity=row.get("quantity"),
                    metadata=row,
                )
            )

        return matches


ADAPTERS: dict[str, RetailerAdapter] = {
    "catalog": CatalogOnlyAdapter()
}


def get_adapter(retailer: str | None) -> RetailerAdapter:
    return ADAPTERS.get(
        (retailer or "catalog").lower(),
        ADAPTERS["catalog"],
    )
