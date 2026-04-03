# SHELF-SCOUTER

**Multi-frame shelf scanning for grocery platforms** (Instacart, delivery services, etc.)  
Uses **Gemma 4** — Google DeepMind's multimodal vision model — to detect and identify
labelled products on store shelves in real time.

A **React Native / Expo** mobile client captures 3–5 best-quality frames, attaches QGPS
metadata (GPS + device orientation), and sends them to the **Flask + Gemma 4** backend
which fuses the frames into a single authoritative shelf analysis.

---

## Features

| Capability | Details |
|---|---|
| 📷 Smart Scan Mode | Auto-captures the 3–5 best frames per session |
| 🎯 Frame quality analysis | Stability (accelerometer) + brightness filtering |
| 🔀 Multi-frame fusion | De-duplication, confidence boosting, coverage expansion |
| 📍 QGPS Layer | GPS coordinates + device orientation per session |
| 🏪 Store mapping | GPS → nearest store; orientation → aisle/shelf |
| 🏷️ Label OCR | Reads brand names, product text, and identifiers |
| 📦 Quantity estimation | Estimates visible units per product |
| 🤖 Function calling | Structured JSON via Gemma 4 native function calling |
| 🌐 REST API | Session-based HTTP endpoints for mobile + IoT clients |
| 🔒 SSRF hardening | HTTPS enforcement, private-IP blocking, DNS-rebinding protection |

---

## Architecture

```
┌─────────────────────────────────────┐
│   React Native / Expo (mobile/)     │
│                                     │
│  CameraScreen                       │
│    Smart Scan Mode (auto-capture)   │
│    Frame quality (stable + lit)     │
│    BoundingBoxOverlay (react-svg)   │
│    ScanFeedback ("Hold steady…")    │
│                                     │
│  QGPS Layer                         │
│    expo-location  → GPS coords      │
│    expo-sensors   → pitch/yaw/roll  │
│                                     │
│  Upload flow                        │
│    /scan/session/start              │
│    /scan/session/<id>/frame  ×3–5   │
│    /scan/session/<id>/finalize      │
│                                     │
│  ResultsScreen                      │
│    Products, confidence, aisle      │
└─────────────┬───────────────────────┘
              │ HTTPS REST
┌─────────────▼───────────────────────┐
│   Flask REST API  (app.py)          │
│                                     │
│  POST /scan/session/start           │
│  POST /scan/session/<id>/frame      │
│  POST /scan/session/<id>/finalize   │
│  GET  /scan/session/<id>            │
│  POST /scan          (single-frame) │
│  POST /scan/url                     │
│  POST /search                       │
│  GET  /health                       │
│                                     │
│  sessions.py  – in-memory store     │
│  multi_frame.py – fusion engine     │
│  store_mapping.py – GPS/orientation │
└─────────────┬───────────────────────┘
              │
┌─────────────▼───────────────────────┐
│  Gemma 4  (google-generativeai)     │
│  • model: gemma-4-e4b-it            │
│  • Vision encoder                   │
│  • Function calling → report_prods  │
└─────────────────────────────────────┘
```

---

## Quick Start

### Backend

#### 1. Install dependencies

```bash
pip install -r requirements.txt
```

#### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and set your GOOGLE_API_KEY
```

Get a free API key at <https://aistudio.google.com/>.

#### 3. Run the server

```bash
python app.py
# or for production:
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

#### 4. Run tests

```bash
python tests.py
# 38 tests covering endpoints, multi-frame fusion, and store mapping
```

---

### Mobile Client

```bash
cd mobile
npm install
npx expo start
```

Set `apiBaseUrl` in `mobile/app.json → extra` to your backend URL:

```json
"extra": { "apiBaseUrl": "https://your-backend.example.com" }
```

---

## API Reference

### `GET /health`

```json
{ "status": "ok", "model": "gemma-4-e4b-it" }
```

---

### Session Endpoints (multi-frame scanning)

#### `POST /scan/session/start`

Start a new session with QGPS metadata.

**Request**
```json
{
  "gps":         { "latitude": 37.7749, "longitude": -122.4194, "accuracy": 5.0 },
  "orientation": { "pitch": 0.0, "yaw": 45.0, "roll": 0.0 },
  "store_id":    "store-001"
}
```

**Response** `201`
```json
{
  "session_id": "3fa85f64-...",
  "store_id":   "store-001",
  "aisle":      "Aisle 2 – Beverages",
  "shelf":      "middle shelf",
  "timestamp":  "2026-04-03T10:00:00+00:00"
}
```

---

#### `POST /scan/session/<id>/frame`

Upload and process a single frame.

**Request**
```json
{
  "image":       "<base64 JPEG>",
  "frame_index": 0,
  "query":       "orange juice"
}
```

**Response** `200`
```json
{
  "session_id":  "3fa85f64-...",
  "frame_index": 0,
  "frame_count": 1,
  "result":      { "products": [...], "shelf_summary": "...", "total_unique_products": 3, "model": "gemma-4-e4b-it" }
}
```

---

#### `POST /scan/session/<id>/finalize`

Fuse all uploaded frames and return the merged result.

**Response** `200`
```json
{
  "session_id":            "3fa85f64-...",
  "store_id":              "store-001",
  "aisle":                 "Aisle 2 – Beverages",
  "shelf":                 "middle shelf",
  "products":              [...],
  "shelf_summary":         "Beverage aisle – juices and soft drinks.",
  "total_unique_products": 7,
  "frames_processed":      4,
  "model":                 "gemma-4-e4b-it"
}
```

---

#### `GET /scan/session/<id>`

Retrieve the current state of a session.

---

### Single-frame Endpoints

#### `POST /scan`

Scan a base-64 encoded shelf image (single frame, no session required).

#### `POST /scan/url`

Scan a public HTTPS image URL (SSRF-hardened).

#### `POST /search`

Search for a specific product. Returns filtered `matches` list and `found` boolean.

---

## Multi-Frame Intelligence Engine (`multi_frame.py`)

1. **Aggregate** — collect all product detections from every frame
2. **De-duplicate** — merge products by normalised name
3. **Max quantity** — keep the highest unit count seen across frames
4. **Best label text** — keep the most descriptive label string
5. **Confidence boost** — products seen in ≥ 2 frames are promoted one level (`low → medium`, `medium → high`)
6. **Coverage expansion** — unique products from all frames are included
7. **Best summary** — the longest shelf summary from any frame wins

---

## Store Mapping Service (`store_mapping.py`)

- `map_gps(lat, lng)` → nearest `store_id` within 500 m, or `None`
- `map_orientation(store_id, pitch, yaw, roll)` → `{"aisle": ..., "shelf": ...}`
- Uses the Haversine formula for GPS distance
- Per-store yaw-to-aisle and pitch-to-shelf lookup tables (swap for a real DB)

---

## Mobile App Structure (`mobile/`)

```
mobile/
├── App.tsx                         # Navigation root
├── app.json                        # Expo config + API URL
├── package.json
├── tsconfig.json
└── src/
    ├── types/index.ts              # Shared TypeScript types
    ├── services/
    │   ├── api.ts                  # Backend HTTP client
    │   └── qgps.ts                 # GPS + orientation capture
    ├── hooks/
    │   └── useFrameQuality.ts      # Accelerometer stability + brightness
    ├── components/
    │   ├── ScanFeedback.tsx        # Real-time status overlay
    │   └── BoundingBoxOverlay.tsx  # SVG bounding boxes
    └── screens/
        ├── CameraScreen.tsx        # Smart Scan + upload flow
        └── ResultsScreen.tsx       # Fused results display
```

---

## Model Selection

Set `GEMMA_MODEL` in `.env`:

| Model | Use case |
|---|---|
| `gemma-4-e2b-it` | Fastest – mobile / edge devices |
| `gemma-4-e4b-it` | Balanced – **default** |
| `gemma-4-26b-a4b-it` | High accuracy, MoE efficiency |
| `gemma-4-31b-it` | Maximum accuracy |

---

## License

Apache 2.0
