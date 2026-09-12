# HOARE Admission Boundary Verification

**Date:** 2026-09-12
**System:** SHELF-SCOUTER + HOARE admission boundary
**Purpose:** Preserve provenance for trusted physical-identity and execution-admission verification.

## Live negative-path verification

A real phone image was submitted to the mobile gateway.

Gemini identified Arm & Hammer Baking Soda and additional shelf products.

The frame contained:

- physical_identity_verified = false
- physical_identity_gtin = null
- server barcode evidence = unavailable

The verify endpoint returned:

    authorized_adapter = catalog-only
    status = UNKNOWN
    verified = false
    reason = trusted_retailer_evidence_unavailable

The admission endpoint returned:

    decision = ESCALATE
    identity.status = INFERRED
    identity.verified = false
    reason = product_identity_not_verified

The pick endpoint was then tested with the AI-generated candidate.

The resource route independently returned:

    decision = ALLOW
    provider = edge
    region = edge-local

HOARE nevertheless returned:

    status = ESCALATE
    action = RECAPTURE_OR_TARGETED_VERIFICATION
    reason = product_identity_not_verified

Therefore resource authorization cannot override product-identity authorization.

## Positive-path regression verification

Server-side authorized barcode test:

    test_barcode_first_gateway.py::test_server_barcode_authorized_match_skips_gemini

Result:

    1 passed

Integrated trusted-evidence/admission suite:

    test_barcode_first_gateway.py
    test_trusted_product_evidence.py
    test_hoare_pick_admission_path.py
    test_hoare_pick_integration.py

Result:

    25 passed

## Security invariants

1. AI observation is not equivalent to physical identity.
2. Client-supplied barcode data is not trusted as physical evidence.
3. Physical identity must originate from server-controlled evidence.
4. Retailer authorization is separated from AI inference.
5. Resource authorization is separated from action authorization.
6. Unverified identity cannot reach the existing pick executor.
7. Resource ALLOW cannot override product-identity ESCALATE.

## Execution invariant

    PICK_EXECUTION_REQUIRES:
        verified_physical_identity
        AND
        authorized_resource_route
        AND
        valid_request_context

## Architecture

    PHONE CAMERA
        |
        v
    SHELF-SCOUTER
        |
        v
    AI OBSERVATION
        |
        v
    SERVER-CONTROLLED PHYSICAL EVIDENCE
        |
        v
    RETAILER ADAPTER
        |
        v
    TRUSTED IDENTITY
        |
        v
    HOARE ADMISSION
        |
        v
    RESOURCE AUTHORITY
        |
        v
    EXISTING EXECUTOR

## Proven control-plane separation

Negative path:

    AI candidate
        |
        v
    physical identity NOT verified
        |
        v
    resource ALLOW
        |
        v
    HOARE ESCALATE
        |
        v
    executor blocked

Positive regression path:

    server barcode
        |
        v
    authorized retailer GTIN
        |
        v
    trusted physical identity
        |
        v
    HOARE admission
        |
        v
    existing execution path

This establishes SHELF-SCOUTER as a governed HOARE vertical rather than an application that bypasses the HOARE admission boundary.

## Provenance

This record preserves the SHELF-SCOUTER/HOARE admission architecture and verification evidence as of 2026-09-12.
