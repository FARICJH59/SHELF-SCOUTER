"""Phone-first gateway for SHELF-SCOUTER.

This is intentionally additive: it wraps the existing app.py service instead of
replacing it. It provides a stable /v1 surface for the mobile picking client and
can later be placed behind HOARE/AEGIS and Triton without changing the phone UI.
"""

import os
from datetime import datetime, timezone
from uuid import uuid4

from flask import jsonify, request

from app import app, scan_shelf_image, _decode_image, _sessions, GOOGLE_API_KEY


def _session(session_id):
    return _sessions.get(session_id)


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

    frame = {
        "frame_id": str(uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "query": payload.get("query"),
        "gps": payload.get("gps"),
        "qgps": payload.get("qgps"),
        "orientation": payload.get("orientation"),
        "result": result
    }
    session["frames"].append(frame)
    return jsonify(frame)


@app.post("/v1/sessions/<session_id>/pick")
def v1_pick(session_id):
    session = _session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    payload = request.get_json(silent=True) or {}
    if not payload.get("product"):
        return jsonify({"error": "Missing 'product'"}), 400

    pick = {
        "pick_id": str(uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "product": payload["product"],
        "sku": payload.get("sku"),
        "quantity": payload.get("quantity", 1),
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
