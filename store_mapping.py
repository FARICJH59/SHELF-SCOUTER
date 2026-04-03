"""
Store mapping service.

Converts raw GPS coordinates and device orientation into human-readable
store / aisle / shelf context.

    map_gps(lat, lng) → store_id | None
    map_orientation(store_id, pitch, yaw, roll) → {"aisle": ..., "shelf": ...}

The sample store catalogue and floor-plan data below are illustrative; in
production they should be backed by a database or spatial index.
"""

import math
from typing import Optional


# ---------------------------------------------------------------------------
# Sample store catalogue
# Replace with a database query / spatial index in production.
# ---------------------------------------------------------------------------
_STORES: list[dict] = [
    {
        "store_id": "store-001",
        "name": "Main Street Grocery",
        "lat": 37.7749,
        "lng": -122.4194,
    },
    {
        "store_id": "store-002",
        "name": "Bay Area Supermarket",
        "lat": 37.3382,
        "lng": -121.8863,
    },
    {
        "store_id": "store-003",
        "name": "Oakland Fresh Market",
        "lat": 37.8044,
        "lng": -122.2712,
    },
]

# Maximum great-circle distance (km) to consider a GPS fix "inside" a store.
_MAX_STORE_RADIUS_KM: float = 0.5

# ---------------------------------------------------------------------------
# Orientation-to-aisle/shelf mapping per store
#
# yaw_aisles:   map compass-bearing (yaw in degrees, –180..180) to aisle name
# pitch_shelves: map tilt angle (pitch in degrees) to shelf row label
# ---------------------------------------------------------------------------
_ORIENTATION_MAP: dict[str, dict] = {
    "store-001": {
        "yaw_aisles": [
            {"range": (-45, 45), "aisle": "Aisle 1 – Dairy"},
            {"range": (45, 135), "aisle": "Aisle 2 – Beverages"},
            {"range": (135, 180), "aisle": "Aisle 3 – Snacks"},
            {"range": (-180, -135), "aisle": "Aisle 3 – Snacks"},
            {"range": (-135, -45), "aisle": "Aisle 4 – Produce"},
        ],
        "pitch_shelves": [
            {"range": (10, 90), "shelf": "top shelf"},
            {"range": (-10, 10), "shelf": "middle shelf"},
            {"range": (-90, -10), "shelf": "bottom shelf"},
        ],
    },
    "store-002": {
        "yaw_aisles": [
            {"range": (-60, 60), "aisle": "Aisle A – Fresh Produce"},
            {"range": (60, 120), "aisle": "Aisle B – Frozen Foods"},
            {"range": (120, 180), "aisle": "Aisle C – Bakery"},
            {"range": (-180, -120), "aisle": "Aisle C – Bakery"},
            {"range": (-120, -60), "aisle": "Aisle D – Beverages"},
        ],
        "pitch_shelves": [
            {"range": (10, 90), "shelf": "top shelf"},
            {"range": (-10, 10), "shelf": "middle shelf"},
            {"range": (-90, -10), "shelf": "bottom shelf"},
        ],
    },
    "store-003": {
        "yaw_aisles": [
            {"range": (-90, 0), "aisle": "Aisle I – Dairy & Eggs"},
            {"range": (0, 90), "aisle": "Aisle II – Meat & Seafood"},
            {"range": (90, 180), "aisle": "Aisle III – Pantry"},
            {"range": (-180, -90), "aisle": "Aisle IV – Health & Beauty"},
        ],
        "pitch_shelves": [
            {"range": (10, 90), "shelf": "top shelf"},
            {"range": (-10, 10), "shelf": "middle shelf"},
            {"range": (-90, -10), "shelf": "bottom shelf"},
        ],
    },
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return the great-circle distance in kilometres between two GPS points."""
    R = 6_371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(a))


def _find_label(ranges: list[dict], value: float, default: str = "unknown") -> str:
    """Return the label for the first range that contains *value*."""
    for entry in ranges:
        lo, hi = entry["range"]
        if lo <= value < hi:
            return entry.get("aisle") or entry.get("shelf") or default
    return default


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def map_gps(lat: float, lng: float) -> Optional[str]:
    """
    Return the ``store_id`` of the nearest store within
    ``_MAX_STORE_RADIUS_KM`` km, or ``None`` if no store is nearby.
    """
    best_store: Optional[dict] = None
    best_dist = float("inf")

    for store in _STORES:
        dist = _haversine(lat, lng, store["lat"], store["lng"])
        if dist < best_dist:
            best_dist = dist
            best_store = store

    if best_store is not None and best_dist <= _MAX_STORE_RADIUS_KM:
        return best_store["store_id"]
    return None


def map_orientation(store_id: str, pitch: float, yaw: float, roll: float) -> dict:
    """
    Map device orientation angles to aisle / shelf context for *store_id*.

    Args:
        store_id: Store identifier returned by :func:`map_gps`.
        pitch: Device pitch in degrees (–90 to 90).
        yaw: Device yaw / compass heading in degrees (–180 to 180).
        roll: Device roll in degrees (unused, reserved for future use).

    Returns:
        ``{"aisle": "<aisle name>", "shelf": "<shelf label>"}``
    """
    layout = _ORIENTATION_MAP.get(store_id)
    if not layout:
        return {"aisle": "unknown", "shelf": "unknown"}

    aisle = _find_label(layout.get("yaw_aisles", []), yaw)
    shelf = _find_label(layout.get("pitch_shelves", []), pitch)

    return {"aisle": aisle, "shelf": shelf}


def get_store_info(store_id: str) -> Optional[dict]:
    """Return the store catalogue entry for *store_id*, or ``None``."""
    for store in _STORES:
        if store["store_id"] == store_id:
            return store
    return None
