"""Governed remediation proposal boundary for HOARE.

Provenance: 2026-09-13.

A diagnostic report may explain a failure and suggest bounded next steps, but
those suggestions are not executable authority. This module converts a
DiagnosticReport into a canonical, immutable proposal envelope that can be
submitted back to HOARE/AEGIS admission.

Security invariant:
    diagnostic proposal != authorization != execution
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from hoare_debugging_agent import DiagnosticDisposition, DebuggingReport


SCHEMA_VERSION = "hoare.remediation-proposal.v1"
PROPOSER_VERSION = "1.0.0"


class RemediationProposalError(ValueError):
    """Raised when a diagnostic report cannot produce a safe proposal."""


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class RemediationProposal:
    schema: str
    proposer_version: str
    proposal_id: str
    session_id: str
    execution_id: str | None
    disposition: str
    action: str
    evidence_refs: tuple[str, ...]
    execution_boundary: Mapping[str, Any]
    proposal_hash: str
    authority: str = "proposal-only"
    can_execute: bool = False

    def unsigned_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "proposer_version": self.proposer_version,
            "proposal_id": self.proposal_id,
            "session_id": self.session_id,
            "execution_id": self.execution_id,
            "disposition": self.disposition,
            "action": self.action,
            "evidence_refs": list(self.evidence_refs),
            "execution_boundary": dict(self.execution_boundary),
            "authority": self.authority,
            "can_execute": self.can_execute,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self.unsigned_payload()
        payload["proposal_hash"] = self.proposal_hash
        return payload


def compile_remediation_proposal(
    *,
    report: DebuggingReport,
    proposal_id: str,
    action: str,
) -> RemediationProposal:
    """Compile a diagnostic finding into a non-executable proposal.

    HEALTHY reports cannot generate remediation. CRITICAL findings may only
    generate proposals whose action is explicitly operator-oriented; the
    proposal still has no authority to execute.
    """
    if not proposal_id or not action:
        raise RemediationProposalError("proposal_identity_required")
    if report.disposition is DiagnosticDisposition.HEALTHY:
        raise RemediationProposalError("healthy_execution_requires_no_remediation")
    if not report.findings:
        raise RemediationProposalError("proposal_requires_diagnostic_finding")

    allowed_actions = {
        finding_action
        for finding in report.findings
        for finding_action in finding.proposed_actions
    }
    if action not in allowed_actions:
        raise RemediationProposalError("proposal_action_not_present_in_diagnostics")

    refs = tuple(
        ref
        for finding in report.findings
        for ref in finding.evidence_refs
        if ref
    )
    normalized_refs = tuple(dict.fromkeys(refs))

    boundary = report.metadata.get("execution_boundary", {})
    if not isinstance(boundary, Mapping):
        boundary = {}
    normalized_boundary = dict(boundary)

    unsigned = {
        "schema": SCHEMA_VERSION,
        "proposer_version": PROPOSER_VERSION,
        "proposal_id": proposal_id,
        "session_id": report.session_id,
        "execution_id": report.execution_id,
        "disposition": report.disposition.value,
        "action": action,
        "evidence_refs": list(normalized_refs),
        "execution_boundary": normalized_boundary,
        "authority": "proposal-only",
        "can_execute": False,
    }
    proposal_hash = _sha256(unsigned)

    return RemediationProposal(
        schema=SCHEMA_VERSION,
        proposer_version=PROPOSER_VERSION,
        proposal_id=proposal_id,
        session_id=report.session_id,
        execution_id=report.execution_id,
        disposition=report.disposition.value,
        action=action,
        evidence_refs=normalized_refs,
        execution_boundary=normalized_boundary,
        proposal_hash=proposal_hash,
        authority="proposal-only",
        can_execute=False,
    )


__all__ = [
    "PROPOSER_VERSION",
    "RemediationProposal",
    "RemediationProposalError",
    "SCHEMA_VERSION",
    "compile_remediation_proposal",
]
