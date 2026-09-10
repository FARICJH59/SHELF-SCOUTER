"""Phone-first gateway for SHELF-SCOUTER.

This wraps the existing Gemma service and provides a stable retailer-neutral
surface for a grocery picking client. Retailer credentials stay server-side.
"""

import os
from datetime import datetime, timezone
from uuid import uuid4

from flask import jsonify, request

from app import app, scan_shelf_image, _decode_image, _sessions, GOOGLE_API_KEY
from retailer_adapters import get_adapter


def _session(session_id):
    return _sessions.get(session_id)


def _match_requested_item(result: dict, query: str | None, barcode: str | None = None) -> dict:
    """Return a deterministic pick recommendation from vision results.

    This is intentionally conservative. It does not claim SKU identity unless
    a retailer/catalog adapter supplies one. A future HOARE admission layer can
    apply tenant/order policy before a pick is confirmed.
    """
    products = result.get("products", [])
    q = (query or "").strip().lower()
    candidates = []
    for product in products:
        name = str(product.get("name", ""))
        label = str(product.get("label_text", ""))
        haystack = f"{name} {label}".lower()
        score = 0
        if q and q in haystack:
            score += 100
        if barcode and barcode in haystack:
            score += 200
        if q:
            score += sum(1 for token in q.split() if token in haystack) * 10
        confidence = str(product.get("confidence", "")).lower()
        score += {"high": 5, "medium": 2}.get(confidence, 0)
        if score:
            candidates.append((score, product))
    candidates.sort(key=lambda item: item[0], reverse=True)
    if not candidates:
        return {"found": False, "action": "KEEP_SCANNING", "candidate": None}
    return {"found": True, "action": "VERIFY_AND_PICK", "candidate": candidates[0][1], "score": candidates[0][0]}


@app.get("/v1/health")
def v1_health():
    return jsonify({"status": "ok", "service": "shelf-scouter-mobile-gateway", "ai_configured": bool(GOOGLE_API_KEY)})


@app.post("/v1/sessions")
def v1_create_session():
    payload = request.get_json(silent=True) or {}
    session_id = str(uuid4())
    _sessions[session_id] = {
        "session_id": session_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "device_id": payload.get("device_id"),
        "retailer": payload.get("retailer"),
        "store_id": payload.get("store_id"),
        "order_id": payload.get("order_id"),
        "gps": payload.get("gps"),
        "qgps": payload.get("qgps"),
        "orientation": payload.get("orientation"),
        "frames": [],
        "picks": []
    }
    return jsonify({"session_id": session_id, "status": "active"})


@app.post("/v1/sessions/<session_id>/frames")
def v1_frame(session_id):
    session = _session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    if not GOOGLE_API_KEY:
        return jsonify({"error": "GOOGLE_API_KEY not configured"}), 503

    payload = request.get_json(silent=True) or {}
    image_data = payload.get("image")
    if not image_data:
        return jsonify({"error": "Missing 'image' field"}), 400

    try:
        image = _decode_image(image_data)
        result = scan_shelf_image(image, payload.get("query"))
    except Exception:
        return jsonify({"error": "Inference failed"}), 500

    match = _match_requested_item(result, payload.get("query"), payload.get("barcode"))
    frame = {
        "frame_id": str(uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "query": payload.get("query"),
        "barcode": payload.get("barcode"),
        "gps": payload.get("gps"),
        "qgps": payload.get("qgps"),
        "orientation": payload.get("orientation"),
        "result": result,
        "pick_match": match
    }
    session["frames"].append(frame)
    return jsonify(frame)


@app.post("/v1/sessions/<session_id>/resolve")
def v1_resolve(session_id):
    session = _session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    payload = request.get_json(silent=True) or {}
    query = str(payload.get("query", "")).strip()
    if not query:
        return jsonify({"error": "Missing 'query'"}), 400
    adapter = get_adapter(session.get("retailer"))
    items = adapter.resolve_item(query=query, store_id=session.get("store_id"), barcode=payload.get("barcode"))
    return jsonify({
        "retailer": session.get("retailer") or "catalog",
        "query": query,
        "authorized_adapter": adapter.name,
        "candidates": [item.__dict__ for item in items]
    })


@app.post("/v1/sessions/<session_id>/pick")
def v1_pick(session_id):
    session = _session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    payload = request.get_json(silent=True) or {}
    if not payload.get("product"):
        return jsonify({"error": "Missing 'product'"}), 400
    quantity = int(payload.get("quantity", 1))
    if quantity < 1:
        return jsonify({"error": "quantity must be >= 1"}), 400

    pick = {
        "pick_id": str(uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "product": payload["product"],
        "sku": payload.get("sku"),
        "gtin": payload.get("gtin"),
        "quantity": quantity,
        "source_frame_id": payload.get("source_frame_id"),
        "status": "confirmed"
    }
    session["picks"].append(pick)
    return jsonify(pick)


@app.get("/v1/sessions/<session_id>")
def v1_session(session_id):
    session = _session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    return jsonify(session)


if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", "5000"))
    app.run(host=host, port=port)
