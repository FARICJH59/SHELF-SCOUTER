"""
SHELF-SCOUTER – Gemma 4 powered shelf-scanning service.

Analyses shelf images from IoT cameras / grocery-platform uploads and returns
structured product information using Gemma 4's multimodal vision capabilities.
"""

import base64
import ipaddress
import json
import logging
import os
import socket
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import requests as http_requests
from pyzbar import pyzbar

import google.generativeai as genai
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from PIL import Image

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
# Barcode utilities
# ---------------------------------------------------------------------------

# Barcode types that carry a product GTIN / EAN / UPC suitable for
# Open Food Facts lookups.
_GTIN_BARCODE_TYPES = frozenset(
    ["EAN13", "EAN8", "UPCA", "UPCE", "ISBN10", "ISBN13"]
)

# Open Food Facts product endpoint – no API key required.
_OFF_URL = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json?fields=product_name,brands,categories,quantity,image_url"


def _decode_barcodes(image: Image.Image) -> list[dict]:
    """
    Decode all barcodes present in *image* using pyzbar.

    Returns a list of dicts with keys:
        ``type``    – barcode symbology (e.g. 'EAN13', 'QRCODE')
        ``data``    – decoded payload string
        ``rect``    – bounding box as {left, top, width, height}
    """
    decoded = pyzbar.decode(image)
    results = []
    for obj in decoded:
        results.append(
            {
                "type": obj.type,
                "data": obj.data.decode("utf-8", errors="replace"),
                "rect": {
                    "left": obj.rect.left,
                    "top": obj.rect.top,
                    "width": obj.rect.width,
                    "height": obj.rect.height,
                },
            }
        )
    return results


def _lookup_barcode_product(barcode: str) -> dict | None:
    """
    Look up a GTIN/EAN/UPC barcode on Open Food Facts.

    Returns a dict with product metadata on success, or ``None`` if the
    product is not found or the request fails.
    """
    try:
        resp = http_requests.get(
            _OFF_URL.format(barcode=barcode),
            timeout=10,
            headers={"User-Agent": "SHELF-SCOUTER/1.0"},
        )
        if resp.status_code != 200:
            return None
        body = resp.json()
        if body.get("status") != 1:
            return None
        p = body.get("product", {})
        return {
            "product_name": p.get("product_name"),
            "brands": p.get("brands"),
            "categories": p.get("categories"),
            "quantity": p.get("quantity"),
            "image_url": p.get("image_url"),
        }
    except Exception:
        logger.debug("Open Food Facts lookup failed for barcode %s", barcode)
        return None


# ---------------------------------------------------------------------------
# In-memory session store
# NOTE: Sessions are stored in process memory and will not persist across
# server restarts. For production use, replace with a persistent store
# (e.g., Redis or a database).
# ---------------------------------------------------------------------------
_sessions: dict = {}


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


@app.route("/scan/session/start", methods=["POST"])
def session_start():
    """
    Create a new scanning session with optional GPS/QGPS context.

    Accepts JSON body:
        {
            "gps":         { "lat": <float>, "lng": <float>, "accuracy": <float> },
            "qgps":        { "x": <float>, "y": <float>, "z": <float>,
                             "floor": <int>, "accuracy_mm": <float> },
            "orientation": { "pitch": <float>, "yaw": <float>, "roll": <float> },
            "device_id":   "<string>"
        }

    Returns:
        { "session_id": "<uuid>" }
    """
    payload = request.get_json(silent=True) or {}
    session_id = str(uuid.uuid4())
    _sessions[session_id] = {
        "session_id": session_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "gps": payload.get("gps"),
        "qgps": payload.get("qgps"),
        "orientation": payload.get("orientation"),
        "device_id": payload.get("device_id"),
        "frames": [],
    }
    logger.info("Session created: %s (device=%s)", session_id, payload.get("device_id"))
    return jsonify({"session_id": session_id})


@app.route("/scan/session/<session_id>/export", methods=["GET"])
def session_export(session_id: str):
    """
    Export all scan data collected during a session.

    Returns:
        {
            "session_id": "<uuid>",
            "created_at": "<ISO-8601 timestamp>",
            "gps":        { ... },
            "qgps":       { ... },
            "orientation":{ ... },
            "device_id":  "<string>",
            "frames":     [ ... ]
        }
    """
    session = _sessions.get(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    return jsonify(session)


@app.route("/barcode", methods=["POST"])
def barcode():
    """
    Decode barcodes from a shelf image.

    Accepts JSON body:
        {
            "image":  "<base64-encoded image or data URL>",
            "lookup": true   // optional; look up product info on Open Food Facts
        }

    Returns:
        {
            "barcodes": [
                {
                    "type": "EAN13",
                    "data": "5012345678900",
                    "rect": { "left": 10, "top": 20, "width": 80, "height": 40 },
                    "product": { ... }   // present when lookup=true and product found
                },
                ...
            ],
            "total": <int>
        }
    """
    payload = request.get_json(silent=True) or {}
    image_data = payload.get("image")
    if not image_data:
        return jsonify({"error": "Missing 'image' field"}), 400

    try:
        image = _decode_image(image_data)
    except Exception:
        logger.exception("Failed to decode image")
        return jsonify({"error": "Invalid image data"}), 400

    try:
        barcodes = _decode_barcodes(image)
    except Exception:
        logger.exception("Barcode detection failed")
        return jsonify({"error": "Barcode detection failed"}), 500

    if payload.get("lookup"):
        for bc in barcodes:
            if bc["type"] in _GTIN_BARCODE_TYPES:
                product_info = _lookup_barcode_product(bc["data"])
                if product_info:
                    bc["product"] = product_info

    return jsonify({"barcodes": barcodes, "total": len(barcodes)})


@app.route("/barcode/url", methods=["POST"])
def barcode_url():
    """
    Decode barcodes from a shelf image provided as a public URL.

    Accepts JSON body:
        {
            "url":    "<public https image URL>",
            "lookup": true   // optional; look up product info on Open Food Facts
        }

    Returns the same structure as POST /barcode.
    The URL must use https and resolve to a public IP address.
    """
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

    try:
        barcodes = _decode_barcodes(image)
    except Exception:
        logger.exception("Barcode detection failed")
        return jsonify({"error": "Barcode detection failed"}), 500

    if payload.get("lookup"):
        for bc in barcodes:
            if bc["type"] in _GTIN_BARCODE_TYPES:
                product_info = _lookup_barcode_product(bc["data"])
                if product_info:
                    bc["product"] = product_info

    return jsonify({"barcodes": barcodes, "total": len(barcodes)})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    logger.info("Starting SHELF-SCOUTER on %s:%d (model=%s)", host, port, GEMMA_MODEL)
    app.run(host=host, port=port, debug=debug)
