"""Governed remediation coordinator tests.

Provenance: 2026-09-13.
"""

from dataclasses import replace

import pytest

from hoare_pick_admission import AdmissionDecision, ResourceRoute
from hoare_remediation_coordinator import (
    RemediationCoordinatorError,
    coordinate_remediation,
)
from product_verification import verify_product
from test_hoare_remediation_execution import _candidate, SECRET


def _verified_identity():
    return verify_product(
        requested_sku="sku-1",
        detected_sku="sku-1",
    )


def _route(decision=AdmissionDecision.ALLOW):
    return ResourceRoute(
        decision=decision,
        provider="test-provider",
        region="test-region",
    )


def test_coordinator_requires_fresh_allow_and_prepares_signed_execution():
    result = coordinate_remediation(
        candidate=_candidate(),
        identity=_verified_identity(),
        source_frame_id="frame-remediation",
        evidence_signature="evidence-signature",
        capability_version="1.0.0",
        contract_version="1.0.0",
        request_id="coordinator-request-1",
        secret=SECRET,
        resource_route=_route(),
        now=1000.0,
    )

    assert result.admission.decision is AdmissionDecision.ALLOW
    assert result.execution.allowed is True
    assert result.execution.request.request_id == "coordinator-request-1"
    assert result.execution.request.plan_hash == result.execution.plan.plan_hash
    assert result.execution.binding.proposal_id == "proposal-1"


def test_coordinator_stops_on_resource_deny():
    with pytest.raises(
        RemediationCoordinatorError,
        match="remediation_execution_requires_fresh_allow_admission",
    ):
        coordinate_remediation(
            candidate=_candidate(),
            identity=_verified_identity(),
            source_frame_id="frame-remediation",
            evidence_signature="evidence-signature",
            capability_version="1.0.0",
            contract_version="1.0.0",
            request_id="coordinator-request-2",
            secret=SECRET,
            resource_route=_route(AdmissionDecision.DENY),
            now=1000.0,
        )


def test_coordinator_stops_on_identity_not_verified():
    identity = verify_product(requested_sku="sku-1", detected_sku="other-sku")

    with pytest.raises(
        RemediationCoordinatorError,
        match="remediation_execution_requires_fresh_allow_admission",
    ):
        coordinate_remediation(
            candidate=_candidate(),
            identity=identity,
            source_frame_id="frame-remediation",
            evidence_signature="evidence-signature",
            capability_version="1.0.0",
            contract_version="1.0.0",
            request_id="coordinator-request-3",
            secret=SECRET,
            resource_route=_route(),
            now=1000.0,
        )


def test_coordinator_rejects_executable_candidate_before_admission():
    candidate = replace(_candidate(), can_execute=True)

    with pytest.raises(
        RemediationCoordinatorError,
        match="candidate_must_not_be_executable",
    ):
        coordinate_remediation(
            candidate=candidate,
            identity=_verified_identity(),
            source_frame_id="frame-remediation",
            evidence_signature="evidence-signature",
            capability_version="1.0.0",
            contract_version="1.0.0",
            request_id="coordinator-request-4",
            secret=SECRET,
            resource_route=_route(),
            now=1000.0,
        )
