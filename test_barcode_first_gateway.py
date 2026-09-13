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

    def resolve_item(self, *, query, store_id=None, barcode=None):
        if query.strip() == FakeItem.sku:
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

def test_gda_recovered_barcode_requires_physical_verification(monkeypatch):
    app = mobile_gateway.app
    app.testing = True

    class EmptyBarcodeDecoder:
        def decode(self, image_bytes):
            return []

    class FakeGDARecovery:
        def recover(self, image_bytes, *, session_id, source_frame_id):
            assert image_bytes
            assert session_id
            assert source_frame_id

            return type(
                "RecoveryResult",
                (),
                {
                    "values": [FakeItem.gtin],
                    "attempts": 1,
                    "diagnosis": "DIRECT_BARCODE_NOT_FOUND",
                    "route": "GDA_BARCODE_RECOVERY",
                },
            )()

    class VerifiedPhysicalIdentity:
        def verify(
            self,
            *,
            image_bytes,
            requested_sku,
            expected_gtin=None,
        ):
            assert image_bytes
            assert requested_sku == FakeItem.sku
            assert expected_gtin == FakeItem.gtin
            return True

    monkeypatch.setattr(
        mobile_gateway,
        "_BARCODE_DECODER",
        EmptyBarcodeDecoder(),
    )
    monkeypatch.setattr(
        mobile_gateway,
        "_GDA_BARCODE_RECOVERY",
        FakeGDARecovery(),
    )
    monkeypatch.setattr(
        mobile_gateway,
        "_PHYSICAL_IDENTITY_VERIFIER",
        VerifiedPhysicalIdentity(),
    )
    monkeypatch.setattr(
        mobile_gateway,
        "get_adapter",
        lambda retailer: FakeAdapter(),
    )

    def gemini_must_not_run(*args, **kwargs):
        raise AssertionError(
            "Gemini was invoked after a fully verified GDA barcode recovery"
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
        session_id = response.get_json()["session_id"]

        response = client.post(
            f"/v1/sessions/{session_id}/frames",
            data={
                "image": (
                    io.BytesIO(_image_bytes()),
                    "gda-test.png",
                ),
                "barcode": "CLIENT-SUPPLIED-UNTRUSTED",
            },
            content_type="multipart/form-data",
        )

        assert response.status_code == 200

        frame = response.get_json()

        # GDA recovery must have its own route and provenance.
        assert frame["fast_path"]["route"] == "GDA_BARCODE_RECOVERY"
        assert frame["server_barcode_source"] == "gda_recovery"
        assert frame["server_barcode_match"] == FakeItem.gtin

        assert frame["gda"]["attempted"] is True
        assert frame["gda"]["route"] == "GDA_BARCODE_RECOVERY"
        assert frame["gda"]["physical_identity_verified"] is True

        # The independently verified identity is what authorizes
        # the trusted product identity state.
        assert frame["physical_identity_verified"] is True
        assert frame["physical_identity_gtin"] == FakeItem.gtin

        candidate = frame["pick_match"]["candidate"]

        assert candidate["sku"] == FakeItem.sku
        assert candidate["gtin"] == FakeItem.gtin
        assert (
            candidate["identity_source"]
            == "gda_barcode_physical_verified"
        )

        # The client barcode remains observation-only.
        assert frame["barcode"] == "CLIENT-SUPPLIED-UNTRUSTED"


def test_gda_recovery_does_not_inherit_direct_barcode_fast_path(monkeypatch):
    app = mobile_gateway.app
    app.testing = True

    class EmptyBarcodeDecoder:
        def decode(self, image_bytes):
            return []

    class FakeGDARecovery:
        def recover(self, image_bytes, *, session_id, source_frame_id):
            return type(
                "RecoveryResult",
                (),
                {
                    "values": [FakeItem.gtin],
                    "attempts": 1,
                    "diagnosis": "DIRECT_BARCODE_NOT_FOUND",
                    "route": "GDA_BARCODE_RECOVERY",
                },
            )()

    class VerifiedPhysicalIdentity:
        def verify(
            self,
            *,
            image_bytes,
            requested_sku,
            expected_gtin=None,
        ):
            return True

    monkeypatch.setattr(
        mobile_gateway,
        "_BARCODE_DECODER",
        EmptyBarcodeDecoder(),
    )
    monkeypatch.setattr(
        mobile_gateway,
        "_GDA_BARCODE_RECOVERY",
        FakeGDARecovery(),
    )
    monkeypatch.setattr(
        mobile_gateway,
        "_PHYSICAL_IDENTITY_VERIFIER",
        VerifiedPhysicalIdentity(),
    )
    monkeypatch.setattr(
        mobile_gateway,
        "get_adapter",
        lambda retailer: FakeAdapter(),
    )

    def gemini_must_not_run(*args, **kwargs):
        raise AssertionError(
            "GDA recovery incorrectly fell through to Gemini"
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
        session_id = response.get_json()["session_id"]

        response = client.post(
            f"/v1/sessions/{session_id}/frames",
            data={
                "image": (
                    io.BytesIO(_image_bytes()),
                    "gda-route-test.png",
                ),
            },
            content_type="multipart/form-data",
        )

        assert response.status_code == 200

        frame = response.get_json()

        # This is the critical trust-boundary assertion:
        # a GDA recovery may produce a verified product, but it
        # must never masquerade as the original direct BARCODE_FAST
        # route.
        assert frame["server_barcode_source"] == "gda_recovery"
        assert frame["fast_path"]["route"] == "GDA_BARCODE_RECOVERY"
        assert frame["fast_path"]["route"] != "BARCODE_FAST"

        assert (
            frame["pick_match"]["match_source"]
            == "gda_barcode_physical_verified"
        )


def test_gda_recovered_barcode_cannot_claim_identity_without_physical_verification(
    monkeypatch,
):
    app = mobile_gateway.app
    app.testing = True

    class EmptyBarcodeDecoder:
        def decode(self, image_bytes):
            return []

    class FakeGDARecovery:
        def recover(self, image_bytes, *, session_id, source_frame_id):
            assert image_bytes
            assert session_id
            assert source_frame_id

            return type(
                "RecoveryResult",
                (),
                {
                    "values": [FakeItem.gtin],
                    "attempts": 1,
                    "diagnosis": "DIRECT_BARCODE_NOT_FOUND",
                    "route": "GDA_BARCODE_RECOVERY",
                },
            )()

    class RejectingPhysicalIdentity:
        def verify(
            self,
            *,
            image_bytes,
            requested_sku,
            expected_gtin=None,
        ):
            assert image_bytes
            assert requested_sku == FakeItem.sku
            assert expected_gtin == FakeItem.gtin
            return False

    monkeypatch.setattr(
        mobile_gateway,
        "_BARCODE_DECODER",
        EmptyBarcodeDecoder(),
    )
    monkeypatch.setattr(
        mobile_gateway,
        "_GDA_BARCODE_RECOVERY",
        FakeGDARecovery(),
    )
    monkeypatch.setattr(
        mobile_gateway,
        "_PHYSICAL_IDENTITY_VERIFIER",
        RejectingPhysicalIdentity(),
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

        response = client.post(
            f"/v1/sessions/{session_id}/frames",
            data={
                "image": (
                    io.BytesIO(_image_bytes()),
                    "gda-rejected-test.png",
                ),
            },
            content_type="multipart/form-data",
        )

        # Physical identity was explicitly rejected. The existing
        # gateway therefore remains in its fallback/escalation boundary.
        assert response.status_code == 202

        payload = response.get_json()
        assert isinstance(payload, dict)

        # A diagnostic recovery must never manufacture an authorized
        # physical identity or direct BARCODE_FAST admission.
        assert payload.get("physical_identity_verified") is not True
        assert not payload.get("physical_identity_gtin")
        assert payload.get("fast_path", {}).get("route") != "BARCODE_FAST"
