"""
Unit tests for SHELF-SCOUTER app.py (no live API calls required).
"""

import base64
import json
import sys
import types
import unittest
from io import BytesIO
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Stub out google-generativeai so tests run without the package installed
# ---------------------------------------------------------------------------
genai_stub = types.ModuleType("google.generativeai")
genai_stub.configure = lambda **kw: None

protos_stub = types.ModuleType("google.generativeai.protos")

def _make_proto_class(name):
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
    attrs = {
        "__init__": __init__,
        "OBJECT": "OBJECT",
        "ARRAY": "ARRAY",
        "STRING": "STRING",
        "INTEGER": "INTEGER",
    }
    return type(name, (), attrs)

for cls_name in ("Tool", "FunctionDeclaration", "Schema", "Part", "Type"):
    setattr(protos_stub, cls_name, _make_proto_class(cls_name))

genai_stub.protos = protos_stub
genai_stub.types = types.ModuleType("google.generativeai.types")
genai_stub.types.GenerationConfig = lambda **kw: kw
genai_stub.GenerativeModel = MagicMock()

sys.modules.setdefault("google", types.ModuleType("google"))
sys.modules["google.generativeai"] = genai_stub
sys.modules["google.generativeai.protos"] = protos_stub
sys.modules["google.generativeai.types"] = genai_stub.types

# Stub PIL
pil_stub = types.ModuleType("PIL")
image_mod = types.ModuleType("PIL.Image")

class _FakeImage:
    format = "JPEG"
    def save(self, buf, format="JPEG"):
        buf.write(b"FAKE_IMAGE_DATA")

image_mod.Image = _FakeImage
image_mod.open = lambda buf: _FakeImage()
pil_stub.Image = image_mod

sys.modules.setdefault("PIL", pil_stub)
sys.modules["PIL.Image"] = image_mod

# ---------------------------------------------------------------------------
# Now import app under test
# ---------------------------------------------------------------------------
import importlib
import os
os.environ.setdefault("GOOGLE_API_KEY", "test-key")

import app as shelf_app


def _make_b64_image() -> str:
    """Return a minimal valid base64-encoded JPEG string."""
    return base64.b64encode(b"FAKE").decode()


class TestHealthEndpoint(unittest.TestCase):
    def setUp(self):
        shelf_app.app.config["TESTING"] = True
        self.client = shelf_app.app.test_client()

    def test_health_returns_200(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("model", data)


class TestScanEndpoint(unittest.TestCase):
    def setUp(self):
        shelf_app.app.config["TESTING"] = True
        self.client = shelf_app.app.test_client()

    def _mock_scan_result(self):
        return {
            "products": [
                {
                    "name": "Orange Juice",
                    "category": "beverages",
                    "quantity": 3,
                    "shelf_position": "middle",
                    "label_text": "Tropicana Orange Juice 1L",
                    "confidence": "high",
                }
            ],
            "shelf_summary": "Beverage shelf with juices.",
            "total_unique_products": 1,
            "model": "gemma-4-e4b-it",
        }

    def test_scan_missing_image_returns_400(self):
        resp = self.client.post(
            "/scan", json={}, content_type="application/json"
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    def test_scan_invalid_image_returns_400(self):
        resp = self.client.post(
            "/scan",
            json={"image": "not-valid-base64!!!"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_scan_returns_products(self):
        with patch.object(shelf_app, "scan_shelf_image", return_value=self._mock_scan_result()):
            resp = self.client.post(
                "/scan",
                json={"image": _make_b64_image()},
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("products", data)
        self.assertEqual(len(data["products"]), 1)
        self.assertEqual(data["products"][0]["name"], "Orange Juice")

    def test_scan_with_query(self):
        with patch.object(shelf_app, "scan_shelf_image", return_value=self._mock_scan_result()) as mock_fn:
            resp = self.client.post(
                "/scan",
                json={"image": _make_b64_image(), "query": "juice"},
                content_type="application/json",
            )
            mock_fn.assert_called_once()
            _, search_query = mock_fn.call_args.args
            self.assertEqual(search_query, "juice")
        self.assertEqual(resp.status_code, 200)


class TestSearchEndpoint(unittest.TestCase):
    def setUp(self):
        shelf_app.app.config["TESTING"] = True
        self.client = shelf_app.app.test_client()

    def _mock_result(self):
        return {
            "products": [
                {
                    "name": "Orange Juice",
                    "category": "beverages",
                    "quantity": 3,
                    "shelf_position": "middle",
                    "label_text": "Tropicana Orange Juice 1L",
                    "confidence": "high",
                },
                {
                    "name": "Milk",
                    "category": "dairy",
                    "quantity": 5,
                    "shelf_position": "bottom",
                    "label_text": "Whole Milk 2L",
                    "confidence": "high",
                },
            ],
            "shelf_summary": "Mixed shelf.",
            "total_unique_products": 2,
            "model": "gemma-4-e4b-it",
        }

    def test_search_missing_image_returns_400(self):
        resp = self.client.post("/search", json={"query": "juice"})
        self.assertEqual(resp.status_code, 400)

    def test_search_missing_query_returns_400(self):
        resp = self.client.post("/search", json={"image": _make_b64_image()})
        self.assertEqual(resp.status_code, 400)

    def test_search_found(self):
        with patch.object(shelf_app, "scan_shelf_image", return_value=self._mock_result()):
            resp = self.client.post(
                "/search",
                json={"image": _make_b64_image(), "query": "orange juice"},
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["found"])
        self.assertEqual(len(data["matches"]), 1)
        self.assertEqual(data["matches"][0]["name"], "Orange Juice")

    def test_search_not_found(self):
        with patch.object(shelf_app, "scan_shelf_image", return_value=self._mock_result()):
            resp = self.client.post(
                "/search",
                json={"image": _make_b64_image(), "query": "chips"},
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertFalse(data["found"])
        self.assertEqual(data["matches"], [])


class TestDecodeImage(unittest.TestCase):
    def test_plain_base64(self):
        raw = base64.b64encode(b"TEST").decode()
        img = shelf_app._decode_image(raw)
        self.assertIsNotNone(img)

    def test_data_url(self):
        raw = base64.b64encode(b"TEST").decode()
        data_url = f"data:image/jpeg;base64,{raw}"
        img = shelf_app._decode_image(data_url)
        self.assertIsNotNone(img)


if __name__ == "__main__":
    unittest.main()
