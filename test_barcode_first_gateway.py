from __future__ import annotations

import io
from unittest.mock import patch

from PIL import Image

import mobile_gateway


def _image_bytes() -> bytes:
    image = Image.new("RGB", (64, 64), "white")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


class FakeItem:
    retailer = "catalog"
    store_id = "TEST-STORE"
    sku = "SKU-BARCODE-001"
    gtin = "00012345678905"
    name = "Test Product"
    available = True
    quantity = 3
    metadata = {}


class FakeAdapter:
    name = "test-catalog"

    def resolve_gtin(self, *, gtin, store_id=None):
        if gtin == FakeItem.gtin:
            return [FakeItem()]
        return []


class FakeBarcodeDecoder:
    def decode(self, image_bytes):
        assert image_bytes
        return [FakeItem.gtin]


def test_server_barcode_authorized_match_skips_gemini(monkeypatch):
    app = mobile_gateway.app
    app.testing = True

    monkeypatch.setattr(
        mobile_gateway,
        "_BARCODE_DECODER",
        FakeBarcodeDecoder(),
    )
    monkeypatch.setattr(
        mobile_gateway,
        "get_adapter",
        lambda retailer: FakeAdapter(),
    )

    # Gemini must NOT be touched on the exact authorized barcode path.
    def gemini_must_not_run(*args, **kwargs):
        raise AssertionError(
            "Gemini was invoked even though an authorized server barcode matched"
        )

    monkeypatch.setattr(
        mobile_gateway,
        "scan_shelf_image",
        gemini_must_not_run,
    )

    with app.test_client() as client:
        response = client.post(
            "/v1/sessions",
            json={
                "retailer": "catalog",
                "store_id": "TEST-STORE",
            },
        )

        assert response.status_code == 200
        session = response.get_json()
        session_id = session["session_id"]

        response = client.post(
            f"/v1/sessions/{session_id}/frames",
            data={
                "image": (
                    io.BytesIO(_image_bytes()),
                    "test.png",
                ),
                # This deliberately differs from the server barcode.
                # It must remain observation-only.
                "barcode": "CLIENT-SUPPLIED-UNTRUSTED",
            },
            content_type="multipart/form-data",
        )

        assert response.status_code == 200

        frame = response.get_json()

        assert frame["fast_path"]["route"] == "BARCODE_FAST"
        assert frame["physical_identity_verified"] is True
        assert frame["physical_identity_gtin"] == FakeItem.gtin
        assert frame["server_barcode_match"] == FakeItem.gtin
        assert frame["barcode"] == "CLIENT-SUPPLIED-UNTRUSTED"

        candidate = frame["pick_match"]["candidate"]

        assert candidate["sku"] == FakeItem.sku
        assert candidate["gtin"] == FakeItem.gtin
        assert (
            candidate["identity_source"]
            == "server_barcode_authorized_gtin"
        )


def test_client_barcode_is_not_server_physical_identity(monkeypatch):
    app = mobile_gateway.app
    app.testing = True

    class EmptyBarcodeDecoder:
        def decode(self, image_bytes):
            return []

    monkeypatch.setattr(
        mobile_gateway,
        "_BARCODE_DECODER",
        EmptyBarcodeDecoder(),
    )
    monkeypatch.setattr(
        mobile_gateway,
        "get_adapter",
        lambda retailer: FakeAdapter(),
    )

    with app.test_client() as client:
        response = client.post(
            "/v1/sessions",
            json={
                "retailer": "catalog",
                "store_id": "TEST-STORE",
            },
        )

        assert response.status_code == 200
        session_id = response.get_json()["session_id"]

        # A client-supplied barcode alone must never become physical proof.
        response = client.post(
            f"/v1/sessions/{session_id}/frames",
            data={
                "image": (
                    io.BytesIO(_image_bytes()),
                    "test.png",
                ),
                "barcode": FakeItem.gtin,
            },
            content_type="multipart/form-data",
        )

        # Gemini may be reached after the failed physical barcode path,
        # so the important invariant is that the frame cannot claim
        # server-side physical verification.
        if response.status_code == 200:
            frame = response.get_json()
            assert frame.get("physical_identity_verified") is not True
            assert not frame.get("physical_identity_gtin")
            assert frame.get("server_barcodes") == []
