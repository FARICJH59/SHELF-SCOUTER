"""Phone-first gateway for SHELF-SCOUTER.

The existing scan capability remains intact. The v1 picking surface adds an
additive fast-path, identity-verification, HOARE admission, and execution
feedback boundary before a pick can be confirmed.
"""

import os
from datetime import datetime, timezone
from uuid import uuid4

from flask import jsonify, request

from app import app, scan_shelf_image, _decode_image, _sessions, GOOGLE_API_KEY
from retailer_adapters import get_adapter
from fast_path import build_fast_path, route_fast_path
from product_verification import ProductEvidence, verify_product, identity_summary
from hoare_pick_admission import AdmissionDecision, PickRequest, ResourceRoute, admit_pick
from execution_feedback import ExecutionFeedbackRecorder

_feedback = ExecutionFeedbackRecorder()


def _session(session_id):
    return _sessions.get(session_id)


def _match_requested_item(result: dict, query: str | None, barcode: str | None = None) -> dict:
    """Return a deterministic candidate; never treat it as verified identity."""
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
        score += {"high": 5, "medium": 2}.get(str(product.get("confidence", "")).lower(), 0)
        if score:
            candidates.append((score, product))
    candidates.sort(key=lambda item: item[0], reverse=True)
    if not candidates:
        return {"found": False, "action": "KEEP_SCANNING", "candidate": None}
    return {"found": True, "action": "VERIFY_AND_PICK", "candidate": candidates[0][1], "score": candidates[0][0]}


def _identity_from_frame(frame: dict, requested_sku: str | None = None):
    """Build identity from explicit evidence; vision naming alone is not verification."""
    candidate = (frame.get("pick_match") or {}).get("candidate") or {}
    verification = frame.get("verification") or {}
    detected_sku = verification.get("detected_sku") or candidate.get("sku")
    evidence = []
    if frame.get("barcode"):
        evidence.append(ProductEvidence("barcode", str(frame["barcode"]), 1.0))
    if candidate.get("name"):
        evidence.append(ProductEvidence("vision_name", str(candidate["name"]), 0.70))
    return verify_product(
        requested_sku=requested_sku,
        detected_sku=detected_sku,
        name=candidate.get("name"),
        barcode_match=bool(verification.get("barcode_match")),
        catalog_match=bool(verification.get("catalog_match")),
        visual_match=bool(verification.get("visual_match")),
        ocr_match=bool(verification.get("ocr_match")),
        evidence=evidence,
    )


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
        "tenant_id": payload.get("tenant_id", "default"),
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
        fast = build_fast_path(image)
        route = route_fast_path(fast)
    except Exception:
        return jsonify({"error": "Invalid image data"}), 400
    if route == "VISION_ESCALATION":
        frame = {
            "frame_id": str(uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "query": payload.get("query"),
            "barcode": payload.get("barcode"),
            "fast_path": {"route": route, "quality": fast.quality.__dict__, "image_sha256": fast.image_sha256, "normalized_size": fast.normalized_size},
            "action": "RECAPTURE",
            "result": {"products": [], "total_unique_products": 0},
        }
        session["frames"].append(frame)
        return jsonify(frame), 202
    try:
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
        "fast_path": {"route": route, "quality": fast.quality.__dict__, "image_sha256": fast.image_sha256, "normalized_size": fast.normalized_size},
        "result": result,
        "pick_match": match,
        "action": "VERIFY_IDENTITY" if match.get("found") else "KEEP_SCANNING",
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
    return jsonify({"retailer": session.get("retailer") or "catalog", "query": query, "authorized_adapter": adapter.name, "candidates": [item.__dict__ for item in items]})


@app.post("/v1/sessions/<session_id>/admission")
def v1_admission(session_id):
    """Evaluate a source frame through the additive HOARE pick-admission contract."""
    session = _session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    payload = request.get_json(silent=True) or {}
    frame_id = payload.get("source_frame_id")
    requested_sku = str(payload.get("sku") or "").strip()
    if not frame_id or not requested_sku:
        return jsonify({"error": "source_frame_id and sku are required"}), 400
    frame = next((f for f in session["frames"] if f.get("frame_id") == frame_id), None)
    if not frame:
        return jsonify({"error": "Source frame not found"}), 404
    identity = _identity_from_frame(frame, requested_sku)
    route_payload = payload.get("resource_route") or {}
    try:
        decision = AdmissionDecision(str(route_payload.get("decision", "ALLOW")))
    except ValueError:
        return jsonify({"error": "resource_route.decision must be ALLOW, DENY, or ESCALATE"}), 400
    route = ResourceRoute(decision=decision, provider=route_payload.get("provider"), region=route_payload.get("region"), predicted_latency_ms=route_payload.get("predicted_latency_ms"), reason=route_payload.get("reason", []))
    admission = admit_pick(PickRequest(tenant_id=session.get("tenant_id", "default"), order_id=session.get("order_id") or payload.get("order_id", "unknown"), requested_sku=requested_sku, device_id=session.get("device_id") or "unknown", store_id=session.get("store_id"), aisle=payload.get("aisle"), shelf=payload.get("shelf")), identity, route)
    return jsonify({"decision": admission.decision.value, "reasons": admission.reasons, "identity": identity_summary(identity), "resource_route": route.__dict__, "next_action": "CONFIRM_PICK" if admission.decision is AdmissionDecision.ALLOW else "RECAPTURE_OR_TARGETED_VERIFICATION" if admission.decision is AdmissionDecision.ESCALATE else "STOP"})


@app.post("/v1/sessions/<session_id>/pick")
def v1_pick(session_id):
    session = _session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    payload = request.get_json(silent=True) or {}
    product = payload.get("product")
    requested_sku = str(payload.get("sku") or "").strip()
    source_frame_id = payload.get("source_frame_id")
    if not product or not requested_sku or not source_frame_id:
        return jsonify({"error": "product, sku, and source_frame_id are required"}), 400
    frame = next((f for f in session["frames"] if f.get("frame_id") == source_frame_id), None)
    if not frame:
        return jsonify({"error": "Source frame not found"}), 404
    identity = _identity_from_frame(frame, requested_sku)
    admission = admit_pick(PickRequest(tenant_id=session.get("tenant_id", "default"), order_id=session.get("order_id", "unknown"), requested_sku=requested_sku, device_id=session.get("device_id") or "unknown", store_id=session.get("store_id"), aisle=payload.get("aisle"), shelf=payload.get("shelf")), identity)
    if admission.decision is not AdmissionDecision.ALLOW:
        code = 409 if admission.decision is AdmissionDecision.ESCALATE else 403
        return jsonify({"status": admission.decision.value, "reasons": admission.reasons, "identity": identity_summary(identity), "action": "RECAPTURE_OR_TARGETED_VERIFICATION" if admission.decision is AdmissionDecision.ESCALATE else "STOP"}), code
    quantity = int(payload.get("quantity", 1))
    if quantity < 1:
        return jsonify({"error": "quantity must be >= 1"}), 400
    execution = _feedback.start(tenant_id=session.get("tenant_id", "default"), order_id=session.get("order_id", "unknown"), requested_sku=requested_sku, provider=payload.get("provider", "edge"), region=payload.get("region", "edge-local"), device_id=session.get("device_id") or "unknown", model=(frame.get("result") or {}).get("model", "targeted-vision"))
    completed = _feedback.complete(execution.execution_id, success=True, identity_status=identity.status.value, identity_confidence=identity.confidence)
    pick = {"pick_id": str(uuid4()), "timestamp": datetime.now(timezone.utc).isoformat(), "product": product, "sku": requested_sku, "gtin": payload.get("gtin"), "quantity": quantity, "source_frame_id": source_frame_id, "status": "confirmed", "admission": {"decision": admission.decision.value, "reasons": admission.reasons}, "execution": _feedback.telemetry_observation(completed.execution_id)}
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
