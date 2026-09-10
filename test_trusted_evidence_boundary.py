from dataclasses import asdict

import mobile_gateway
from retailer_adapters import CatalogOnlyAdapter
from trusted_product_evidence import TrustedEvidenceAuthority, verify_against_adapter


def test_future_issued_evidence_is_rejected():
    authority = TrustedEvidenceAuthority("test-secret", ttl_seconds=60)
    evidence = authority.issue(
        session_id="session",
        frame_id="frame",
        requested_sku="SKU-1",
        detected_sku="SKU-1",
        barcode_match=True,
        catalog_match=True,
        now=200,
    )
    assert authority.verify(evidence, now=199) is False
    assert authority.verify(evidence, now=200) is True


def test_wrong_server_decoded_barcode_cannot_establish_physical_identity():
    class Decoder:
        def decode(self, image_bytes):
            return ["012345678906"]

    from physical_identity_verifier import ServerBarcodePhysicalIdentityVerifier

    verifier = ServerBarcodePhysicalIdentityVerifier(Decoder())
    assert verifier.verify(
        image_bytes=b"server-frame",
        requested_sku="SKU-1",
        expected_gtin="012345678905",
    ) is False


def test_client_barcode_does_not_override_missing_physical_verification():
    authority = TrustedEvidenceAuthority("test-secret")
    adapter = CatalogOnlyAdapter([{"sku": "SKU-1", "gtin": "0001", "name": "Item"}])
    evidence = verify_against_adapter(
        authority=authority,
        adapter=adapter,
        session_id="session",
        frame_id="frame",
        requested_sku="SKU-1",
        detected_sku="SKU-1",
        barcode="0001",
        physical_identity_verified=False,
    )
    assert evidence is None


def test_gateway_rejects_trusted_evidence_replayed_to_another_frame_or_session():
    authority = TrustedEvidenceAuthority("test-secret", ttl_seconds=60)
    mobile_gateway._EVIDENCE_AUTHORITY = authority
    evidence = authority.issue(
        session_id="session-a",
        frame_id="frame-a",
        requested_sku="SKU-1",
        detected_sku="SKU-1",
        barcode_match=True,
        catalog_match=True,
        visual_match=True,
        now=100,
    )
    trusted = asdict(evidence)

    valid_frame = {
        "session_id": "session-a",
        "frame_id": "frame-a",
        "trusted_evidence": trusted,
    }
    assert mobile_gateway._trusted_evidence_from_frame(valid_frame) == evidence

    replayed_frame = {
        "session_id": "session-b",
        "frame_id": "frame-b",
        "trusted_evidence": trusted,
    }
    assert mobile_gateway._trusted_evidence_from_frame(replayed_frame) is None


def test_gateway_rejects_evidence_with_same_session_but_different_frame():
    authority = TrustedEvidenceAuthority("test-secret", ttl_seconds=60)
    mobile_gateway._EVIDENCE_AUTHORITY = authority
    evidence = authority.issue(
        session_id="session-a",
        frame_id="frame-a",
        requested_sku="SKU-1",
        detected_sku="SKU-1",
        barcode_match=True,
        catalog_match=True,
        visual_match=True,
        now=100,
    )
    replayed = {
        "session_id": "session-a",
        "frame_id": "frame-b",
        "trusted_evidence": asdict(evidence),
    }
    assert mobile_gateway._trusted_evidence_from_frame(replayed) is None
