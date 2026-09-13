# HOARE Governed Diagnostic Authority — Provenance Record

**Date:** 2026-09-12 10:20 EDT  
**System:** SHELF-SCOUTER / HOARE  
**Purpose:** Governed agentic self-diagnosis and bounded recovery for computer-vision workloads.

## Design decision

SHELF-SCOUTER will use a reusable HOARE **Governed Diagnostic Authority (GDA)** rather than an unrestricted self-debugging agent.

The diagnostic contract is:

`DiagnosticObservation → Diagnosis → RecoveryPlan → DiagnosticAdmission → RecoveryResult → EvidenceAssessment`

## Authority boundary

The diagnostic agent may:

- observe failures;
- diagnose perception/runtime problems;
- propose recovery plans;
- execute only explicitly leased diagnostic actions;
- request additional evidence;
- re-evaluate after recovery.

The diagnostic agent may not:

- self-authorize consequential actions;
- manufacture trusted evidence;
- modify admission policy;
- expand its own permissions;
- bypass AEGIS;
- convert `ESCALATE` into `ALLOW`.

## SHELF-SCOUTER barcode recovery

The first concrete recovery capability is bounded server-side barcode recovery after the direct barcode probe fails. Recovery uses image preprocessing and repeated server-side decoding only. Any decoded GTIN still requires the existing authorized retailer adapter boundary and physical-identity verification before HOARE pick admission.

Client-provided barcode values remain observation-only.

## Bounded recovery controls

Diagnostic leases enforce:

- maximum attempts;
- maximum duration;
- maximum recovery depth;
- maximum compute budget;
- explicit allowed diagnostic actions.

## Security invariant

`DIAGNOSTIC_SUCCESS != ACTION_AUTHORIZATION`

A successful diagnostic recovery only produces additional evidence. It does not authorize the final pick or any other consequential action.

## Planned universalization

The same GDA contract is intended to be reusable for future HOARE computer-vision and autonomous-system verticals, including industrial inspection, robotics, energy equipment, and other governed perception workloads.
