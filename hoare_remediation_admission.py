"""Proposal-to-admission adapter for HOARE/AEGIS.

Provenance: 2026-09-13.

This module is deliberately an adapter, not a second authorization system.
A diagnostic RemediationProposal is validated and bound to a fresh
PickRequest. The resulting candidate can then be evaluated by the existing
provider-neutral ``admit_pick`` authority.

Security invariant:
    proposal != admission != authorization != execution

The adapter never executes, authorizes, or creates an ALLOW decision itself.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any, Mapping

from hoare_pick_admission import (
    PickAdmission,
    PickRequest,
    ResourceRoute,
    admit_pick,
)
from hoare_remediation_proposal import RemediationProposal
from product_verification import ProductIdentity


SCHEMA_VERSION = "hoare.remediation-admission-candidate.v1"
ADAPTER_VERSION = "1.0.0"


class RemediationAdmissionError(ValueError):
    """Raised when a remediation proposal cannot enter admission."""


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _proposal_hash_is_valid(proposal: RemediationProposal) -> bool:
    expected = _sha256(proposal.unsigned_payload())
    return hmac.compare_digest(expected, proposal.proposal_hash)


@dataclass(frozen=True)
class RemediationAdmissionCandidate:
    """Immutable handoff from diagnosis into the existing admission layer."""

    schema: str
    adapter_version: str
    proposal_id: str
    proposal_hash: str
    session_id: str
    execution_id: str | None
    action: str
    request: PickRequest
    evidence_refs: tuple[str, ...]
    execution_boundary: Mapping[str, Any]
    candidate_hash: str
    authority: str = "admission-required"
    can_execute: bool = False

    def unsigned_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "adapter_version": self.adapter_version,
            "proposal_id": self.proposal_id,
            "proposal_hash": self.proposal_hash,
            "session_id": self.session_id,
            "execution_id": self.execution_id,
            "action": self.action,
            "request": {
                "tenant_id": self.request.tenant_id,
                "order_id": self.request.order_id,
                "requested_sku": self.request.requested_sku,
                "device_id": self.request.device_id,
                "store_id": self.request.store_id,
                "aisle": self.request.aisle,
                "shelf": self.request.shelf,
                "intent": self.request.intent,
            },
            "evidence_refs": list(self.evidence_refs),
            "execution_boundary": dict(self.execution_boundary),
            "authority": self.authority,
            "can_execute": self.can_execute,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self.unsigned_payload()
        payload["candidate_hash"] = self.candidate_hash
        return payload


def compile_remediation_admission_candidate(
    *,
    proposal: RemediationProposal,
    request: PickRequest,
) -> RemediationAdmissionCandidate:
    """Bind a valid proposal to a fresh request for the existing admission layer.

    The request context is supplied by the control plane; it is not trusted
    as authorization. The resulting candidate remains non-executable until
    ``admit_remediation_candidate`` invokes the existing ``admit_pick`` path.
    """
    if not _proposal_hash_is_valid(proposal):
        raise RemediationAdmissionError("proposal_hash_invalid")
    if proposal.authority != "proposal-only":
        raise RemediationAdmissionError("proposal_authority_invalid")
    if proposal.can_execute:
        raise RemediationAdmissionError("proposal_must_not_be_executable")
    if not proposal.proposal_id or not proposal.action:
        raise RemediationAdmissionError("proposal_identity_required")
    if not request.tenant_id or not request.order_id or not request.device_id:
        raise RemediationAdmissionError("admission_request_identity_required")
    if not request.requested_sku:
        raise RemediationAdmissionError("admission_request_sku_required")

    # A remediation candidate gets a fresh admission intent. It does not copy
    # the original execution intent and it cannot inherit prior authorization.
    bound_request = PickRequest(
        tenant_id=request.tenant_id,
        order_id=request.order_id,
        requested_sku=request.requested_sku,
        device_id=request.device_id,
        store_id=request.store_id,
        aisle=request.aisle,
        shelf=request.shelf,
        intent=f"hoare_remediation:{proposal.action}",
    )

    unsigned = {
        "schema": SCHEMA_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "proposal_id": proposal.proposal_id,
        "proposal_hash": proposal.proposal_hash,
        "session_id": proposal.session_id,
        "execution_id": proposal.execution_id,
        "action": proposal.action,
        "request": {
            "tenant_id": bound_request.tenant_id,
            "order_id": bound_request.order_id,
            "requested_sku": bound_request.requested_sku,
            "device_id": bound_request.device_id,
            "store_id": bound_request.store_id,
            "aisle": bound_request.aisle,
            "shelf": bound_request.shelf,
            "intent": bound_request.intent,
        },
        "evidence_refs": list(proposal.evidence_refs),
        "execution_boundary": dict(proposal.execution_boundary),
        "authority": "admission-required",
        "can_execute": False,
    }

    return RemediationAdmissionCandidate(
        **unsigned,
        request=bound_request,
        evidence_refs=tuple(unsigned["evidence_refs"]),
        execution_boundary=dict(proposal.execution_boundary),
        candidate_hash=_sha256(unsigned),
    )


def admit_remediation_candidate(
    *,
    candidate: RemediationAdmissionCandidate,
    identity: ProductIdentity,
    resource_route: ResourceRoute | None = None,
) -> PickAdmission:
    """Submit the candidate to the existing HOARE/AEGIS-style pick admission.

    This function intentionally delegates to ``admit_pick``. It does not
    convert a proposal directly into ALLOW, and it does not authorize or
    execute anything.
    """
    expected_hash = _sha256(candidate.unsigned_payload())
    if not hmac.compare_digest(expected_hash, candidate.candidate_hash):
        raise RemediationAdmissionError("candidate_hash_invalid")
    if candidate.authority != "admission-required":
        raise RemediationAdmissionError("candidate_authority_invalid")
    if candidate.can_execute:
        raise RemediationAdmissionError("candidate_must_not_be_executable")

    return admit_pick(
        candidate.request,
        identity,
        resource_route=resource_route,
    )


__all__ = [
    "ADAPTER_VERSION",
    "RemediationAdmissionCandidate",
    "RemediationAdmissionError",
    "SCHEMA_VERSION",
    "admit_remediation_candidate",
    "compile_remediation_admission_candidate",
]
