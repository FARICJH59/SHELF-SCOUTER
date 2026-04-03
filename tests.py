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



# ---------------------------------------------------------------------------
# Tests for multi_frame engine
# ---------------------------------------------------------------------------

import multi_frame as mf


class TestMultiFrameEngine(unittest.TestCase):
    def _product(self, name, confidence="high", quantity=1, label_text="", shelf_position="middle"):
        return {
            "name": name,
            "category": "beverages",
            "confidence": confidence,
            "quantity": quantity,
            "label_text": label_text,
            "shelf_position": shelf_position,
        }

    def test_fuse_empty_frames(self):
        result = mf.fuse_frames([])
        self.assertEqual(result["products"], [])
        self.assertEqual(result["total_unique_products"], 0)
        self.assertEqual(result["frames_processed"], 0)

    def test_fuse_single_frame(self):
        frames = [{"result": {
            "products": [self._product("Milk")],
            "shelf_summary": "Dairy shelf.",
            "total_unique_products": 1,
        }}]
        result = mf.fuse_frames(frames)
        self.assertEqual(len(result["products"]), 1)
        self.assertEqual(result["products"][0]["name"], "Milk")
        self.assertEqual(result["frames_processed"], 1)

    def test_fuse_deduplicates_products(self):
        product_a = self._product("Orange Juice", confidence="low", quantity=2)
        product_b = self._product("Orange Juice", confidence="medium", quantity=3)
        frames = [
            {"result": {"products": [product_a], "shelf_summary": "Juices.", "total_unique_products": 1}},
            {"result": {"products": [product_b], "shelf_summary": "More juices.", "total_unique_products": 1}},
        ]
        result = mf.fuse_frames(frames)
        self.assertEqual(len(result["products"]), 1)
        self.assertEqual(result["products"][0]["quantity"], 3)

    def test_fuse_confidence_boosted_in_multiple_frames(self):
        product_a = self._product("Milk", confidence="low")
        product_b = self._product("Milk", confidence="low")
        frames = [
            {"result": {"products": [product_a], "shelf_summary": "s", "total_unique_products": 1}},
            {"result": {"products": [product_b], "shelf_summary": "s", "total_unique_products": 1}},
        ]
        result = mf.fuse_frames(frames)
        self.assertEqual(result["products"][0]["confidence"], "medium")

    def test_fuse_picks_longest_summary(self):
        frames = [
            {"result": {"products": [], "shelf_summary": "Short.", "total_unique_products": 0}},
            {"result": {"products": [], "shelf_summary": "A much longer shelf summary here.", "total_unique_products": 0}},
        ]
        result = mf.fuse_frames(frames)
        self.assertIn("longer", result["shelf_summary"])

    def test_fuse_expands_coverage(self):
        frames = [
            {"result": {"products": [self._product("Milk")], "shelf_summary": "s", "total_unique_products": 1}},
            {"result": {"products": [self._product("Butter")], "shelf_summary": "s", "total_unique_products": 1}},
        ]
        result = mf.fuse_frames(frames)
        names = {p["name"] for p in result["products"]}
        self.assertIn("Milk", names)
        self.assertIn("Butter", names)
        self.assertEqual(result["total_unique_products"], 2)


# ---------------------------------------------------------------------------
# Tests for store_mapping
# ---------------------------------------------------------------------------

import store_mapping


class TestStoreMapping(unittest.TestCase):
    def test_map_gps_known_store(self):
        # Exactly at Main Street Grocery coordinates
        store_id = store_mapping.map_gps(37.7749, -122.4194)
        self.assertEqual(store_id, "store-001")

    def test_map_gps_no_nearby_store(self):
        # Middle of the Pacific Ocean
        store_id = store_mapping.map_gps(0.0, -150.0)
        self.assertIsNone(store_id)

    def test_map_orientation_known_store(self):
        loc = store_mapping.map_orientation("store-001", pitch=15.0, yaw=0.0, roll=0.0)
        self.assertEqual(loc["aisle"], "Aisle 1 – Dairy")
        self.assertEqual(loc["shelf"], "top shelf")

    def test_map_orientation_unknown_store(self):
        loc = store_mapping.map_orientation("nonexistent", pitch=0.0, yaw=0.0, roll=0.0)
        self.assertEqual(loc["aisle"], "unknown")
        self.assertEqual(loc["shelf"], "unknown")

    def test_map_orientation_bottom_shelf(self):
        loc = store_mapping.map_orientation("store-001", pitch=-20.0, yaw=0.0, roll=0.0)
        self.assertEqual(loc["shelf"], "bottom shelf")

    def test_get_store_info(self):
        info = store_mapping.get_store_info("store-001")
        self.assertIsNotNone(info)
        self.assertEqual(info["name"], "Main Street Grocery")

    def test_get_store_info_missing(self):
        self.assertIsNone(store_mapping.get_store_info("nope"))


# ---------------------------------------------------------------------------
# Tests for session endpoints
# ---------------------------------------------------------------------------

_VALID_GPS = {"latitude": 37.7749, "longitude": -122.4194, "accuracy": 5.0}
_VALID_ORIENTATION = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}


class TestSessionStart(unittest.TestCase):
    def setUp(self):
        shelf_app.app.config["TESTING"] = True
        self.client = shelf_app.app.test_client()

    def test_start_session_returns_201(self):
        resp = self.client.post(
            "/scan/session/start",
            json={"gps": _VALID_GPS, "orientation": _VALID_ORIENTATION},
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()
        self.assertIn("session_id", data)
        self.assertIn("timestamp", data)

    def test_start_session_missing_gps(self):
        resp = self.client.post(
            "/scan/session/start",
            json={"orientation": _VALID_ORIENTATION},
        )
        self.assertEqual(resp.status_code, 400)

    def test_start_session_missing_orientation(self):
        resp = self.client.post(
            "/scan/session/start",
            json={"gps": _VALID_GPS},
        )
        self.assertEqual(resp.status_code, 400)

    def test_start_session_resolves_store(self):
        resp = self.client.post(
            "/scan/session/start",
            json={"gps": _VALID_GPS, "orientation": _VALID_ORIENTATION},
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()
        # Coordinates match store-001
        self.assertEqual(data["store_id"], "store-001")

    def test_start_session_store_id_override(self):
        resp = self.client.post(
            "/scan/session/start",
            json={
                "gps": _VALID_GPS,
                "orientation": _VALID_ORIENTATION,
                "store_id": "store-custom",
            },
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.get_json()["store_id"], "store-custom")


class TestSessionFrameAndFinalize(unittest.TestCase):
    def setUp(self):
        shelf_app.app.config["TESTING"] = True
        self.client = shelf_app.app.test_client()

    def _start_session(self):
        resp = self.client.post(
            "/scan/session/start",
            json={"gps": _VALID_GPS, "orientation": _VALID_ORIENTATION},
        )
        return resp.get_json()["session_id"]

    def _mock_scan_result(self, name="Milk"):
        return {
            "products": [
                {
                    "name": name,
                    "category": "dairy",
                    "quantity": 2,
                    "shelf_position": "middle",
                    "label_text": f"{name} label",
                    "confidence": "high",
                }
            ],
            "shelf_summary": f"Shelf with {name}.",
            "total_unique_products": 1,
            "model": "gemma-4-e4b-it",
        }

    def test_upload_frame_missing_session(self):
        resp = self.client.post(
            "/scan/session/nonexistent-id/frame",
            json={"image": base64.b64encode(b"FAKE").decode()},
        )
        self.assertEqual(resp.status_code, 404)

    def test_upload_frame_missing_image(self):
        sid = self._start_session()
        resp = self.client.post(f"/scan/session/{sid}/frame", json={})
        self.assertEqual(resp.status_code, 400)

    def test_upload_frame_success(self):
        sid = self._start_session()
        with patch.object(shelf_app, "scan_shelf_image", return_value=self._mock_scan_result()):
            resp = self.client.post(
                f"/scan/session/{sid}/frame",
                json={"image": base64.b64encode(b"FAKE").decode(), "frame_index": 0},
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["session_id"], sid)
        self.assertEqual(data["frame_index"], 0)
        self.assertEqual(data["frame_count"], 1)

    def test_finalize_no_frames(self):
        sid = self._start_session()
        resp = self.client.post(f"/scan/session/{sid}/finalize")
        self.assertEqual(resp.status_code, 400)

    def test_finalize_success(self):
        sid = self._start_session()
        with patch.object(shelf_app, "scan_shelf_image", return_value=self._mock_scan_result("Butter")):
            self.client.post(
                f"/scan/session/{sid}/frame",
                json={"image": base64.b64encode(b"FAKE").decode()},
            )
        resp = self.client.post(f"/scan/session/{sid}/finalize")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["session_id"], sid)
        self.assertIn("products", data)
        self.assertEqual(data["frames_processed"], 1)

    def test_finalize_twice_returns_409(self):
        sid = self._start_session()
        with patch.object(shelf_app, "scan_shelf_image", return_value=self._mock_scan_result()):
            self.client.post(
                f"/scan/session/{sid}/frame",
                json={"image": base64.b64encode(b"FAKE").decode()},
            )
        self.client.post(f"/scan/session/{sid}/finalize")
        resp = self.client.post(f"/scan/session/{sid}/finalize")
        self.assertEqual(resp.status_code, 409)

    def test_get_session_state(self):
        sid = self._start_session()
        resp = self.client.get(f"/scan/session/{sid}")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["session_id"], sid)
        self.assertEqual(data["status"], "open")
        self.assertEqual(data["frame_count"], 0)

    def test_get_session_not_found(self):
        resp = self.client.get("/scan/session/does-not-exist")
        self.assertEqual(resp.status_code, 404)

    def test_multi_frame_fusion_end_to_end(self):
        """Two frames with the same product should boost confidence."""
        sid = self._start_session()
        low_conf_result = {
            "products": [
                {
                    "name": "Orange Juice",
                    "category": "beverages",
                    "quantity": 1,
                    "shelf_position": "middle",
                    "label_text": "OJ",
                    "confidence": "low",
                }
            ],
            "shelf_summary": "Juice shelf.",
            "total_unique_products": 1,
            "model": "gemma-4-e4b-it",
        }
        with patch.object(shelf_app, "scan_shelf_image", return_value=low_conf_result):
            for i in range(2):
                self.client.post(
                    f"/scan/session/{sid}/frame",
                    json={"image": base64.b64encode(b"FAKE").decode(), "frame_index": i},
                )
        resp = self.client.post(f"/scan/session/{sid}/finalize")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["total_unique_products"], 1)
        # After two frames, "low" → "medium"
        self.assertEqual(data["products"][0]["confidence"], "medium")


if __name__ == "__main__":
    unittest.main()
