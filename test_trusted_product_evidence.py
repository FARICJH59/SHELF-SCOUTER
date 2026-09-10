from trusted_product_evidence import TrustedEvidenceAuthority, TrustedProductEvidence, verify_against_adapter
from retailer_adapters import CatalogOnlyAdapter
from physical_identity_verifier import RejectByDefaultPhysicalIdentityVerifier


def test_client_cannot_forge_trusted_evidence():
    authority = TrustedEvidenceAuthority("test-secret", ttl_seconds=60)
    evidence = authority.issue(
        session_id="session", frame_id="frame", requested_sku="SKU-1",
        detected_sku="SKU-1", barcode_match=True, catalog_match=True,
    )
    assert authority.verify(evidence)
    forged = TrustedProductEvidence(
        session_id=evidence.session_id, frame_id=evidence.frame_id,
        requested_sku=evidence.requested_sku, detected_sku="EVIL-SKU",
        barcode_match=evidence.barcode_match, catalog_match=evidence.catalog_match,
        visual_match=evidence.visual_match, ocr_match=evidence.ocr_match,
        issuer=evidence.issuer, issued_at=evidence.issued_at,
        expires_at=evidence.expires_at, signature=evidence.signature,
    )
    assert authority.verify(forged) is False


def test_expired_evidence_is_rejected():
    authority = TrustedEvidenceAuthority("test-secret", ttl_seconds=10)
    evidence = authority.issue(
        session_id="session", frame_id="frame", requested_sku="SKU-1",
        detected_sku="SKU-1", barcode_match=True, catalog_match=True, now=100,
    )
    assert authority.verify(evidence, now=110)
    assert authority.verify(evidence, now=111) is False


def test_unconfigured_authority_issues_no_evidence():
    authority = TrustedEvidenceAuthority(None)
    adapter = CatalogOnlyAdapter([{"sku": "SKU-1", "gtin": "0001", "name": "Item"}])
    evidence = verify_against_adapter(
        authority=authority, adapter=adapter, session_id="session", frame_id="frame",
        requested_sku="SKU-1", detected_sku="SKU-1", barcode="0001",
        physical_identity_verified=True,
    )
    assert evidence is None


def test_authorized_adapter_can_issue_matching_evidence_after_physical_verification():
    authority = TrustedEvidenceAuthority("test-secret")
    adapter = CatalogOnlyAdapter([{"sku": "SKU-1", "gtin": "0001", "name": "Item"}])
    evidence = verify_against_adapter(
        authority=authority, adapter=adapter, session_id="session", frame_id="frame",
        requested_sku="SKU-1", detected_sku="SKU-1", barcode="0001",
        physical_identity_verified=True,
    )
    assert evidence is not None
    assert evidence.catalog_match is True
    assert evidence.barcode_match is True
    assert evidence.visual_match is True
    assert authority.verify(evidence) is True


def test_catalog_valid_model_sku_without_physical_verification_cannot_issue_evidence():
    authority = TrustedEvidenceAuthority("test-secret")
    adapter = CatalogOnlyAdapter([{"sku": "SKU-1", "gtin": "0001", "name": "Item"}])
    evidence = verify_against_adapter(
        authority=authority, adapter=adapter, session_id="session", frame_id="frame",
        requested_sku="SKU-1", detected_sku="SKU-1", barcode=None,
    )
    assert evidence is None


def test_client_barcode_alone_cannot_issue_evidence():
    authority = TrustedEvidenceAuthority("test-secret")
    adapter = CatalogOnlyAdapter([{"sku": "SKU-1", "gtin": "0001", "name": "Item"}])
    evidence = verify_against_adapter(
        authority=authority, adapter=adapter, session_id="session", frame_id="frame",
        requested_sku="SKU-1", detected_sku=None, barcode="0001",
        physical_identity_verified=True,
    )
    assert evidence is None


def test_mismatched_detected_sku_cannot_issue_evidence():
    authority = TrustedEvidenceAuthority("test-secret")
    adapter = CatalogOnlyAdapter([
        {"sku": "SKU-1", "gtin": "0001", "name": "Item"},
        {"sku": "OTHER", "gtin": "9999", "name": "Other"},
    ])
    evidence = verify_against_adapter(
        authority=authority, adapter=adapter, session_id="session", frame_id="frame",
        requested_sku="SKU-1", detected_sku="OTHER", barcode="0001",
        physical_identity_verified=True,
    )
    assert evidence is None


def test_default_physical_verifier_fails_closed():
    verifier = RejectByDefaultPhysicalIdentityVerifier()
    assert verifier.verify(image_bytes=b"frame", requested_sku="SKU-1", expected_gtin="0001") is False
