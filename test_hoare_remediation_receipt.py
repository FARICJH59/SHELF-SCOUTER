"""Remediation receipt-boundary tests.

Provenance: 2026-09-13.
"""

from dataclasses import replace

import pytest

from hoare_execution_request import ExecutionReceipt
from hoare_remediation_execution import (
    RemediationExecutionError,
    finalize_remediation_receipt,
    prepare_remediation_execution,
)
from test_hoare_remediation_execution import _allow_admission, _candidate, SECRET


def test_authorized_remediation_can_finalize_normal_signed_receipt():
    authorized = prepare_remediation_execution(
        candidate=_candidate(),
        admission=_allow_admission(),
        source_frame_id="frame-remediation",
        evidence_signature="evidence-signature",
        capability_version="1.0.0",
        contract_version="1.0.0",
        request_id="remediation-receipt-1",
        secret=SECRET,
        now=1000.0,
    )

    receipt = finalize_remediation_receipt(
        authorized=authorized,
        execution_id="execution-remediation-1",
        status="SUCCEEDED",
        result={"remediation": "revalidate_inputs", "verified": True},
        secret=SECRET,
        observed_at=1001.0,
    )

    assert isinstance(receipt, ExecutionReceipt)
    assert receipt.request_hash == authorized.request.request_hash
    assert receipt.execution_id == "execution-remediation-1"
    assert receipt.status == "SUCCEEDED"
    assert receipt.signature


def test_unauthorized_remediation_cannot_finalize_receipt():
    authorized = prepare_remediation_execution(
        candidate=_candidate(),
        admission=_allow_admission(),
        source_frame_id="frame-remediation",
        evidence_signature="evidence-signature",
        capability_version="1.0.0",
        contract_version="1.0.0",
        request_id="remediation-receipt-2",
        secret=SECRET,
        now=1000.0,
    )
    unauthorized = replace(
        authorized,
        authorization=replace(authorized.authorization, allowed=False),
    )

    with pytest.raises(
        RemediationExecutionError,
        match="remediation_receipt_requires_authorization",
    ):
        finalize_remediation_receipt(
            authorized=unauthorized,
            execution_id="execution-remediation-2",
            status="SUCCEEDED",
            result={"remediation": "revalidate_inputs"},
            secret=SECRET,
            observed_at=1001.0,
        )
