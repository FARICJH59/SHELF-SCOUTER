# SHELF-SCOUTER

**IoT-powered shelf scanning for grocery platforms** (Instacart, delivery services, etc.)  
Uses **Gemma 4** — Google DeepMind's multimodal vision model — to detect and identify
labelled products on store shelves in real time.

---

## Features

| Capability | Details |
|---|---|
| 📷 Image scanning | Detects every product on a shelf from a single photo |
| 🔍 Product search | Search for a specific item and get its shelf location |
| 🏷️ Label OCR | Reads brand names, product text, and identifiers |
| 📦 Quantity estimation | Estimates how many units of each product are visible |
| 🤖 Function calling | Structured JSON output via Gemma 4 native function calling |
| 🌐 REST API | Simple HTTP endpoints for IoT devices and web clients |

---

## Architecture

```
IoT Camera / Mobile App
        │
        ▼  (base64 image or URL)
┌───────────────────┐
│  Flask REST API   │  /scan  /scan/url  /search  /health
└────────┬──────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│  Gemma 4 (google-generativeai SDK)               │
│  • Model: gemma-4-e4b-it  (configurable)         │
│  • Vision encoder: ~150 M parameters             │
│  • Function calling → structured product list    │
└──────────────────────────────────────────────────┘
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and set your GOOGLE_API_KEY
```

Get a free API key at <https://aistudio.google.com/>.

### 3. Run the server

```bash
python app.py
# or for production:
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

---

## API Reference

### `GET /health`
Liveness check.

```json
{ "status": "ok", "model": "gemma-4-e4b-it" }
```

---

### `POST /scan`
Scan a shelf image and return all detected products.

**Request**
```json
{
  "image": "<base64-encoded image or data URL>",
  "query": "orange juice"
}
```

**Response**
```json
{
  "products": [
    {
      "name": "Tropicana Orange Juice",
      "category": "beverages",
      "quantity": 3,
      "shelf_position": "middle",
      "label_text": "Tropicana Pure Premium Orange Juice 1.75L No Pulp",
      "confidence": "high"
    }
  ],
  "shelf_summary": "Beverage aisle – refrigerated juices and soft drinks.",
  "total_unique_products": 1,
  "model": "gemma-4-e4b-it"
}
```

---

### `POST /scan/url`
Same as `/scan` but accepts a public image URL instead of base64.

**Request**
```json
{
  "url": "https://example.com/shelf.jpg",
  "query": "milk"
}
```

---

### `POST /search`
Search for a specific product. Returns all scan results plus a filtered
`matches` list and a `found` boolean.

**Request**
```json
{
  "image": "<base64 image>",
  "query": "whole milk"
}
```

**Response** *(adds these fields to the standard scan response)*
```json
{
  "matches": [ { ...product... } ],
  "found": true,
  "query": "whole milk"
}
```

---

## Model Selection

Set `GEMMA_MODEL` in `.env` to choose a model based on your hardware:

| Model | Use case |
|---|---|
| `gemma-4-e2b-it` | Fastest – mobile / edge devices |
| `gemma-4-e4b-it` | Balanced – default recommendation |
| `gemma-4-26b-a4b-it` | High accuracy, MoE efficiency |
| `gemma-4-31b-it` | Maximum accuracy |

All models support image input. E2B and E4B additionally support audio.

---

## Running Tests

```bash
python -m pytest tests.py -v
# or
python tests.py
```

---

## License

Apache 2.0
