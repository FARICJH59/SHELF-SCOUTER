"""
SHELF-SCOUTER – Gemma 4 powered shelf-scanning service.

Analyses shelf images from IoT cameras / grocery-platform uploads and returns
structured product information using Gemma 4's multimodal vision capabilities.

Session endpoints enable multi-frame scanning:
    POST /scan/session/start          – create a session with QGPS metadata
    POST /scan/session/<id>/frame     – upload and process a single frame
    POST /scan/session/<id>/finalize  – fuse all frames and return final result
    GET  /scan/session/<id>           – retrieve session state
"""

import base64
import json
import logging
import os
from io import BytesIO
from pathlib import Path

import google.generativeai as genai
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from PIL import Image

import multi_frame as mf
import sessions as session_store
import store_mapping

load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s – %(message)s",
)
logger = logging.getLogger("shelf-scouter")

# ---------------------------------------------------------------------------
# Gemma 4 client setup
# ---------------------------------------------------------------------------
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GEMMA_MODEL = os.getenv("GEMMA_MODEL", "gemma-4-e4b-it")

if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
else:
    logger.warning("GOOGLE_API_KEY not set – AI endpoints will return errors.")

# Gemma 4 recommended sampling parameters (from model card)
GENERATION_CONFIG = genai.types.GenerationConfig(
    temperature=1.0,
    top_p=0.95,
    top_k=64,
)

# ---------------------------------------------------------------------------
# Product-detection function schema (Gemma 4 native function calling)
# ---------------------------------------------------------------------------
PRODUCT_TOOLS = [
    genai.protos.Tool(
        function_declarations=[
            genai.protos.FunctionDeclaration(
                name="report_products",
                description=(
                    "Report the list of products detected on the shelf. "
                    "Call this once with ALL detected products."
                ),
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "products": genai.protos.Schema(
                            type=genai.protos.Type.ARRAY,
                            description="List of products found on the shelf",
                            items=genai.protos.Schema(
                                type=genai.protos.Type.OBJECT,
                                properties={
                                    "name": genai.protos.Schema(
                                        type=genai.protos.Type.STRING,
                                        description="Product or brand name",
                                    ),
                                    "category": genai.protos.Schema(
                                        type=genai.protos.Type.STRING,
                                        description=(
                                            "Product category, e.g. 'dairy', "
                                            "'beverages', 'snacks', 'produce'"
                                        ),
                                    ),
                                    "quantity": genai.protos.Schema(
                                        type=genai.protos.Type.INTEGER,
                                        description="Estimated number of units visible",
                                    ),
                                    "shelf_position": genai.protos.Schema(
                                        type=genai.protos.Type.STRING,
                                        description=(
                                            "Position on shelf: "
                                            "'top', 'middle', 'bottom', or 'unknown'"
                                        ),
                                    ),
                                    "label_text": genai.protos.Schema(
                                        type=genai.protos.Type.STRING,
                                        description="Any readable text from the product label",
                                    ),
                                    "confidence": genai.protos.Schema(
                                        type=genai.protos.Type.STRING,
                                        description="Detection confidence: 'high', 'medium', or 'low'",
                                    ),
                                },
                                required=["name", "category", "confidence"],
                            ),
                        ),
                        "shelf_summary": genai.protos.Schema(
                            type=genai.protos.Type.STRING,
                            description="Brief human-readable summary of the shelf contents",
                        ),
                        "total_unique_products": genai.protos.Schema(
                            type=genai.protos.Type.INTEGER,
                            description="Total count of unique product types found",
                        ),
                    },
                    required=["products", "shelf_summary", "total_unique_products"],
                ),
            )
        ]
    )
]

# System prompt – thinking disabled for fast inference; enable by prepending <|think|>
SYSTEM_PROMPT = (
    "You are an expert retail shelf analyst for a grocery platform. "
    "When given an image of a store shelf, identify every visible product with precision. "
    "Read all visible label text, brand names, and product identifiers. "
    "Use the report_products function to return a structured list of all detected items."
)

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _decode_image(data: str) -> Image.Image:
    """Decode a base-64-encoded image string (with or without data-URL prefix)."""
    if "," in data:
        data = data.split(",", 1)[1]
    raw = base64.b64decode(data)
    return Image.open(BytesIO(raw))


def _image_to_part(image: Image.Image) -> genai.protos.Part:
    """Convert a PIL Image to a Gemma-compatible inline image Part."""
    buffer = BytesIO()
    fmt = image.format or "JPEG"
    image.save(buffer, format=fmt)
    return {
        "inline_data": {
            "mime_type": f"image/{fmt.lower()}",
            "data": base64.b64encode(buffer.getvalue()).decode(),
        }
    }


def scan_shelf_image(image: Image.Image, search_query: str | None = None) -> dict:
    """
    Run Gemma 4 vision inference on a shelf image.

    Args:
        image: PIL Image of the shelf.
        search_query: Optional product name / query to focus the scan.

    Returns:
        Structured dict with detected products and shelf summary.
    """
    model = genai.GenerativeModel(
        model_name=GEMMA_MODEL,
        generation_config=GENERATION_CONFIG,
        system_instruction=SYSTEM_PROMPT,
        tools=PRODUCT_TOOLS,
    )

    user_text = (
        f"Scan this shelf image and find: {search_query}"
        if search_query
        else "Scan this shelf image and identify all visible products."
    )

    response = model.generate_content(
        [_image_to_part(image), user_text],
        tool_config={
                # ANY mode forces the model to call one of the provided functions,
                # guaranteeing structured JSON output instead of free-form text.
                "function_calling_config": {"mode": "ANY"}
            },
    )

    # Extract function call result
    for part in response.candidates[0].content.parts:
        if part.function_call and part.function_call.name == "report_products":
            args = dict(part.function_call.args)
            products = []
            for p in args.get("products", []):
                products.append(dict(p))
            return {
                "products": products,
                "shelf_summary": args.get("shelf_summary", ""),
                "total_unique_products": args.get("total_unique_products", len(products)),
                "model": GEMMA_MODEL,
            }

    # Fallback: return raw text if function calling didn't trigger
    text = response.text if hasattr(response, "text") else ""
    return {
        "products": [],
        "shelf_summary": text,
        "total_unique_products": 0,
        "model": GEMMA_MODEL,
    }


# ---------------------------------------------------------------------------
# Flask application
# ---------------------------------------------------------------------------
app = Flask(__name__)
CORS(app)


@app.route("/health", methods=["GET"])
def health():
    """Liveness check."""
    return jsonify({"status": "ok", "model": GEMMA_MODEL})


@app.route("/scan", methods=["POST"])
def scan():
    """
    Scan a shelf image and return detected products.

    Accepts JSON body:
        {
            "image": "<base64-encoded image or data URL>",
            "query": "<optional search query>"   // e.g. "orange juice"
        }

    Returns:
        {
            "products": [ { "name", "category", "quantity", "shelf_position",
                            "label_text", "confidence" }, ... ],
            "shelf_summary": "...",
            "total_unique_products": <int>,
            "model": "<model id>"
        }
    """
    if not GOOGLE_API_KEY:
        return jsonify({"error": "GOOGLE_API_KEY not configured"}), 503

    payload = request.get_json(silent=True) or {}
    image_data = payload.get("image")
    if not image_data:
        return jsonify({"error": "Missing 'image' field"}), 400

    try:
        image = _decode_image(image_data)
    except Exception:
        logger.exception("Failed to decode image")
        return jsonify({"error": "Invalid image data"}), 400

    search_query = payload.get("query")

    try:
        result = scan_shelf_image(image, search_query)
    except Exception:
        logger.exception("Gemma 4 inference failed")
        return jsonify({"error": "Inference failed"}), 500

    return jsonify(result)


@app.route("/scan/url", methods=["POST"])
def scan_url():
    """
    Scan a shelf image provided as a public URL.

    Accepts JSON body:
        {
            "url": "<public image URL>",
            "query": "<optional search query>"
        }

    The URL must use https and resolve to a public IP address. The request is
    made directly to the resolved IP (Host header set explicitly) to prevent
    DNS-rebinding SSRF attacks.
    """
    import ipaddress
    import socket
    import requests as http_requests  # local import to avoid shadowing flask.request
    from urllib.parse import urlparse, urlunparse

    if not GOOGLE_API_KEY:
        return jsonify({"error": "GOOGLE_API_KEY not configured"}), 503

    payload = request.get_json(silent=True) or {}
    url = payload.get("url")
    if not url:
        return jsonify({"error": "Missing 'url' field"}), 400

    parsed = urlparse(url)
    if parsed.scheme != "https":
        return jsonify({"error": "Only https URLs are allowed"}), 400

    hostname = parsed.hostname
    if not hostname:
        return jsonify({"error": "Invalid URL: no hostname"}), 400

    try:
        resolved_ip = socket.gethostbyname(hostname)
        ip_obj = ipaddress.ip_address(resolved_ip)
        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved:
            return jsonify({"error": "URL resolves to a non-public address"}), 400
    except Exception:
        return jsonify({"error": "Could not resolve hostname"}), 400

    # Build a safe URL that uses the resolved IP directly so that the DNS
    # lookup cannot be repeated (prevents DNS-rebinding).
    port = parsed.port or 443
    netloc_ip = f"{resolved_ip}:{port}"
    safe_url = urlunparse(parsed._replace(netloc=netloc_ip))

    try:
        resp = http_requests.get(
            safe_url,
            timeout=15,
            headers={"Host": hostname},
            verify=True,
        )
        resp.raise_for_status()
        image = Image.open(BytesIO(resp.content))
    except Exception:
        logger.exception("Failed to fetch image from URL")
        return jsonify({"error": "Could not retrieve image from the provided URL"}), 400

    search_query = payload.get("query")

    try:
        result = scan_shelf_image(image, search_query)
    except Exception:
        logger.exception("Gemma 4 inference failed")
        return jsonify({"error": "Inference failed"}), 500

    return jsonify(result)


@app.route("/search", methods=["POST"])
def search():
    """
    Search for a specific product across a shelf image.

    Accepts JSON body:
        {
            "image": "<base64-encoded image or data URL>",
            "query": "<product name to search for>"
        }

    Returns the same structure as /scan but filtered to products matching
    the query, plus a 'found' boolean field.
    """
    if not GOOGLE_API_KEY:
        return jsonify({"error": "GOOGLE_API_KEY not configured"}), 503

    payload = request.get_json(silent=True) or {}
    image_data = payload.get("image")
    query = payload.get("query", "").strip()

    if not image_data:
        return jsonify({"error": "Missing 'image' field"}), 400
    if not query:
        return jsonify({"error": "Missing 'query' field"}), 400

    try:
        image = _decode_image(image_data)
    except Exception:
        logger.exception("Failed to decode image")
        return jsonify({"error": "Invalid image data"}), 400

    try:
        result = scan_shelf_image(image, query)
    except Exception:
        logger.exception("Gemma 4 inference failed")
        return jsonify({"error": "Inference failed"}), 500

    query_lower = query.lower()
    matches = [
        p for p in result["products"]
        if query_lower in p.get("name", "").lower()
        or query_lower in p.get("label_text", "").lower()
        or query_lower in p.get("category", "").lower()
    ]
    result["matches"] = matches
    result["found"] = len(matches) > 0
    result["query"] = query
    return jsonify(result)


# ---------------------------------------------------------------------------
# Session endpoints (multi-frame scanning)
# ---------------------------------------------------------------------------

@app.route("/scan/session/start", methods=["POST"])
def session_start():
    """
    Start a new multi-frame scanning session.

    Accepts JSON body:
        {
            "gps": {
                "latitude": <float>,
                "longitude": <float>,
                "accuracy": <float>   // metres, optional
            },
            "orientation": {
                "pitch": <float>,     // degrees
                "yaw":   <float>,     // degrees
                "roll":  <float>      // degrees
            },
            "store_id": "<string>"    // optional override
        }

    Returns:
        {
            "session_id": "<uuid>",
            "store_id": "<string | null>",
            "aisle": "<string | null>",
            "shelf": "<string | null>",
            "timestamp": "<ISO-8601>"
        }
    """
    payload = request.get_json(silent=True) or {}

    gps = payload.get("gps")
    orientation = payload.get("orientation")

    if not isinstance(gps, dict):
        return jsonify({"error": "Missing or invalid 'gps' field"}), 400
    if not isinstance(orientation, dict):
        return jsonify({"error": "Missing or invalid 'orientation' field"}), 400

    for key in ("latitude", "longitude"):
        if not isinstance(gps.get(key), (int, float)):
            return jsonify({"error": f"gps.{key} must be a number"}), 400

    for key in ("pitch", "yaw", "roll"):
        if not isinstance(orientation.get(key), (int, float)):
            return jsonify({"error": f"orientation.{key} must be a number"}), 400

    # Resolve store from GPS unless caller already supplied one
    store_id: str | None = payload.get("store_id") or store_mapping.map_gps(
        gps["latitude"], gps["longitude"]
    )

    # Resolve aisle/shelf from orientation
    location: dict = {}
    if store_id:
        location = store_mapping.map_orientation(
            store_id, orientation["pitch"], orientation["yaw"], orientation["roll"]
        )

    session = session_store.create_session(
        gps=gps,
        orientation=orientation,
        store_id=store_id,
    )

    # Persist orientation-derived location in the session
    session["aisle"] = location.get("aisle")
    session["shelf"] = location.get("shelf")

    logger.info(
        "Session created: %s  store=%s  aisle=%s",
        session["session_id"],
        store_id,
        location.get("aisle"),
    )

    return jsonify(
        {
            "session_id": session["session_id"],
            "store_id": store_id,
            "aisle": location.get("aisle"),
            "shelf": location.get("shelf"),
            "timestamp": session["timestamp"],
        }
    ), 201


@app.route("/scan/session/<session_id>/frame", methods=["POST"])
def session_upload_frame(session_id: str):
    """
    Upload and process a single frame within an existing session.

    Accepts JSON body:
        {
            "image":       "<base64-encoded image or data URL>",
            "frame_index": <int>,      // 0-based index within the session
            "query":       "<string>"  // optional focus query
        }

    Returns:
        {
            "session_id":  "<uuid>",
            "frame_index": <int>,
            "frame_count": <int>,
            "result": { ...scan result... }
        }
    """
    if not GOOGLE_API_KEY:
        return jsonify({"error": "GOOGLE_API_KEY not configured"}), 503

    session = session_store.get_session(session_id)
    if session is None:
        return jsonify({"error": "Session not found"}), 404
    if session["status"] != "open":
        return jsonify({"error": "Session is already finalised"}), 409

    payload = request.get_json(silent=True) or {}
    image_data = payload.get("image")
    if not image_data:
        return jsonify({"error": "Missing 'image' field"}), 400

    frame_index = payload.get("frame_index", len(session["frames"]))

    try:
        image = _decode_image(image_data)
    except Exception:
        logger.exception("Failed to decode frame image")
        return jsonify({"error": "Invalid image data"}), 400

    search_query = payload.get("query")

    try:
        result = scan_shelf_image(image, search_query)
    except Exception:
        logger.exception("Gemma 4 inference failed for frame")
        return jsonify({"error": "Inference failed"}), 500

    frame_record = {
        "frame_index": frame_index,
        "result": result,
    }

    if not session_store.add_frame(session_id, frame_record):
        return jsonify({"error": "Could not add frame to session"}), 409

    current_session = session_store.get_session(session_id)
    frame_count = len(current_session["frames"]) if current_session else 0

    logger.info("Frame %d added to session %s", frame_index, session_id)

    return jsonify(
        {
            "session_id": session_id,
            "frame_index": frame_index,
            "frame_count": frame_count,
            "result": result,
        }
    )


@app.route("/scan/session/<session_id>/finalize", methods=["POST"])
def session_finalize(session_id: str):
    """
    Finalise a session: fuse all uploaded frames and return the merged result.

    No request body required.

    Returns:
        {
            "session_id":  "<uuid>",
            "store_id":    "<string | null>",
            "aisle":       "<string | null>",
            "shelf":       "<string | null>",
            "products":    [...],
            "shelf_summary":         "<string>",
            "total_unique_products": <int>,
            "frames_processed":      <int>,
            "model":       "<model id>"
        }
    """
    session = session_store.get_session(session_id)
    if session is None:
        return jsonify({"error": "Session not found"}), 404
    if session["status"] == "finalized":
        return jsonify({"error": "Session already finalised", "result": session["result"]}), 409

    frames = session.get("frames", [])
    if not frames:
        return jsonify({"error": "No frames uploaded to this session"}), 400

    fused = mf.fuse_frames(frames)

    # Enrich with store/location context
    fused["store_id"] = session.get("store_id")
    fused["aisle"] = session.get("aisle")
    fused["shelf"] = session.get("shelf")
    fused["session_id"] = session_id

    session_store.finalize_session(session_id, fused)

    logger.info(
        "Session finalised: %s  unique_products=%d  frames=%d",
        session_id,
        fused["total_unique_products"],
        fused["frames_processed"],
    )

    return jsonify(fused)


@app.route("/scan/session/<session_id>", methods=["GET"])
def session_get(session_id: str):
    """
    Retrieve the current state of a scanning session.

    Returns:
        Full session dict (without raw frame images).
    """
    session = session_store.get_session(session_id)
    if session is None:
        return jsonify({"error": "Session not found"}), 404

    # Return a summary without bulky frame image data
    summary = {
        "session_id": session["session_id"],
        "store_id": session.get("store_id"),
        "aisle": session.get("aisle"),
        "shelf": session.get("shelf"),
        "timestamp": session["timestamp"],
        "gps": session["gps"],
        "orientation": session["orientation"],
        "status": session["status"],
        "frame_count": len(session.get("frames", [])),
        "result": session.get("result"),
    }
    return jsonify(summary)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    logger.info("Starting SHELF-SCOUTER on %s:%d (model=%s)", host, port, GEMMA_MODEL)
    app.run(host=host, port=port, debug=debug)
