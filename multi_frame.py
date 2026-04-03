"""
Multi-frame intelligence engine for shelf-scanning sessions.

Aggregates per-frame Gemma 4 results into a single fused output:
    - De-duplicates product detections across frames (by normalised name)
    - Merges quantity (takes the maximum seen)
    - Boosts confidence for products spotted in ≥ 2 frames
    - Expands shelf coverage by keeping all unique products
    - Picks the most informative shelf summary
"""

from typing import Optional


# Numeric weights for confidence levels
_CONFIDENCE_WEIGHT: dict[str, int] = {
    "high": 3,
    "medium": 2,
    "low": 1,
}
_WEIGHT_TO_CONFIDENCE: dict[int, str] = {v: k for k, v in _CONFIDENCE_WEIGHT.items()}


def _confidence_weight(label: str) -> int:
    return _CONFIDENCE_WEIGHT.get(str(label).lower(), 0)


def _merge_products(all_frame_products: list[list[dict]]) -> list[dict]:
    """
    De-duplicate and merge product detections from multiple frames.

    Products are keyed by their lower-cased, stripped name.  For each key
    the engine keeps:
    - highest confidence (or boosts by one level if seen in ≥ 2 frames)
    - maximum quantity estimate
    - most complete label_text (longest string wins)
    - first non-unknown shelf_position
    """
    merged: dict[str, dict] = {}

    for frame_products in all_frame_products:
        for product in frame_products:
            key = product.get("name", "").lower().strip()
            if not key:
                continue

            if key not in merged:
                merged[key] = dict(product)
                merged[key]["_frame_count"] = 1
            else:
                existing = merged[key]
                existing["_frame_count"] = existing.get("_frame_count", 1) + 1

                # Keep highest confidence
                if _confidence_weight(product.get("confidence", "low")) > _confidence_weight(
                    existing.get("confidence", "low")
                ):
                    existing["confidence"] = product["confidence"]

                # Keep maximum quantity
                new_qty = product.get("quantity") or 0
                existing["quantity"] = max(existing.get("quantity") or 0, new_qty)

                # Keep most descriptive label text
                if len(product.get("label_text") or "") > len(existing.get("label_text") or ""):
                    existing["label_text"] = product["label_text"]

                # Keep first concrete shelf position
                current_pos = existing.get("shelf_position") or "unknown"
                new_pos = product.get("shelf_position") or "unknown"
                if current_pos == "unknown" and new_pos != "unknown":
                    existing["shelf_position"] = new_pos

    # Apply multi-frame confidence boost and strip internal tracking field
    result: list[dict] = []
    for product in merged.values():
        frame_count = product.pop("_frame_count", 1)
        if frame_count >= 2:
            current_weight = _confidence_weight(product.get("confidence", "low"))
            boosted_weight = min(current_weight + 1, 3)
            product["confidence"] = _WEIGHT_TO_CONFIDENCE.get(boosted_weight, "high")
        result.append(product)

    return result


def fuse_frames(frames: list[dict]) -> dict:
    """
    Fuse per-frame scan results into a single unified result.

    Args:
        frames: List of frame records, each containing at minimum a ``result``
            key with the output of ``scan_shelf_image``.

    Returns:
        Fused result dict with ``products``, ``shelf_summary``,
        ``total_unique_products``, and ``frames_processed``.
    """
    if not frames:
        return {
            "products": [],
            "shelf_summary": "No frames processed.",
            "total_unique_products": 0,
            "frames_processed": 0,
        }

    all_frame_products: list[list[dict]] = []
    summaries: list[str] = []
    model: Optional[str] = None

    for frame in frames:
        frame_result = frame.get("result") or {}
        products = frame_result.get("products") or []
        all_frame_products.append(products)
        summary = (frame_result.get("shelf_summary") or "").strip()
        if summary:
            summaries.append(summary)
        if model is None:
            model = frame_result.get("model")

    merged = _merge_products(all_frame_products)

    # Pick most informative summary (longest)
    shelf_summary = max(summaries, key=len) if summaries else "No summary available."

    fused: dict = {
        "products": merged,
        "shelf_summary": shelf_summary,
        "total_unique_products": len(merged),
        "frames_processed": len(frames),
    }
    if model:
        fused["model"] = model

    return fused
