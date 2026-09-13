# HOARE Debugging Agent

**Provenance:** 2026-09-13

## Purpose

The HOARE debugging agent is a provider-neutral diagnostic component. It observes execution evidence and telemetry, classifies failures, and proposes bounded remediation steps.

It is **not** an execution authority.

## Authority boundary

```text
OBSERVE
   ↓
DIAGNOSE
   ↓
PROPOSE
   ↓
HOARE / AEGIS ADMISSION
   ↓
SIGNED EXECUTION REQUEST
   ↓
AUTHORIZED EXECUTOR
   ↓
RECEIPT
```

The debugging agent cannot skip admission, create authorization, or directly execute a proposed action.

## Diagnostic inputs

- session and execution identifiers
- execution status and error information
- latency telemetry
- trusted-evidence state
- execution-authorization state
- references to server-controlled evidence

## Diagnostic outputs

`DebuggingReport` contains:

- schema/version
- session/execution identity
- `HEALTHY`, `INVESTIGATE`, or `ESCALATE` disposition
- structured findings
- evidence references
- proposed diagnostic/remediation actions
- explicit `authority=diagnostic-only`
- explicit `can_execute=false`

## Post-execution telemetry hook

As of **2026-09-13**, `ExecutionFeedbackRecorder.complete()` creates and stores a diagnostic-only report after an execution record is completed. This is an internal control-plane telemetry path: the existing executor result is finalized first, then the debugger observes that result.

The recorder exposes internal diagnostic access through:

- `diagnostic_report(execution_id)`
- `diagnostic_snapshot()`

These reports are not added to the customer-facing pick response.

The diagnostic hook does not authorize, execute, retry, or mutate the signed execution boundary. Any future remediation must return through HOARE/AEGIS admission and the signed execution-request path.

## Execution evidence enrichment

As of **2026-09-13**, the diagnostic report can be enriched after receipt creation with a control-plane-only `execution_boundary` trace. The trace is published by the existing signed execution boundary and attached to the already-created diagnostic report.

The trace records provenance for:

- trusted-evidence signature
- admission decision and a canonical admission hash
- server-authoritative execution-plan hash
- signed execution request ID and request hash
- independent authorization result, reasons, and authorization timestamp
- execution ID
- signed execution receipt hash and signature

The trace is intentionally outside the signed execution request payload. It explains **why and how** an execution reached the executor without changing the authority model or the signed request itself.

The customer-facing `/pick` response is unchanged by this diagnostic enrichment. The trace exists only in the internal diagnostic/control-plane record.

## Governed remediation proposal

As of **2026-09-13**, diagnostic findings can be converted into a `RemediationProposal` by `hoare_remediation_proposal.py`.

A proposal is an **immutable, non-executable handoff** containing:

- proposal ID and schema/version
- originating session/execution identity
- diagnostic disposition
- one action explicitly present in the diagnostic findings
- diagnostic evidence references
- execution-boundary provenance
- canonical proposal hash
- `authority=proposal-only`
- `can_execute=false`

The compiler rejects:

- healthy reports
- reports without findings
- actions that were not proposed by the diagnostic findings

This is intentional: the debugging agent cannot invent an executable fix merely because a caller asks for one.

The proposal is not an execution request. It is the artifact that must be returned to HOARE/AEGIS for a new admission decision. Only a newly admitted action can enter the signed execution-request path.

## Proposal → admission adapter

As of **2026-09-13**, `hoare_remediation_admission.py` provides the next control-plane handoff:

```text
Diagnostic finding
      ↓
RemediationProposal
      ↓
RemediationAdmissionCandidate
      ↓
HOARE / AEGIS admission
      ↓
ExecutionPlan
      ↓
SignedExecutionRequest
      ↓
Authorization
      ↓
Existing Executor
```

`RemediationAdmissionCandidate` is an immutable, non-executable envelope that binds:

- the proposal ID and proposal hash
- session/execution identity
- the proposed action
- a fresh `PickRequest` with a new remediation intent
- diagnostic evidence references
- the original execution-boundary provenance
- a candidate hash
- `authority=admission-required`
- `can_execute=false`

The adapter first recomputes the proposal hash. It rejects invalid proposal authority, executable proposals, missing request identity, and remediation actions that are not supported by this admission adapter.

The adapter then delegates to the **existing** `admit_pick()` authority. It does not manufacture an `ALLOW`, create an authorization, call the executor, or bypass the signed execution-request boundary.

This means a remediation proposal has to earn a new admission decision. Prior execution authorization is never inherited.

The current adapter deliberately supports only the bounded actions `inspect_execution_telemetry` and `revalidate_inputs`. Adding another remediation action requires explicitly adding it to an admission adapter rather than silently broadening authority.

## Safety rules

1. Client observations are never promoted to authority by diagnosis.
2. A missing trusted-evidence boundary is a critical condition.
3. Missing execution authorization is a critical condition.
4. Proposed actions are recommendations only.
5. Post-execution diagnosis cannot alter the already-completed execution result.
6. Diagnostic provenance is not execution authority and is not added to the signed request payload.
7. A remediation proposal is not an authorization and cannot execute itself.
8. Proposal actions must originate in the diagnostic findings; callers cannot inject arbitrary actions.
9. A remediation admission candidate cannot self-authorize; it must pass through the existing admission authority.
10. A new admission does not inherit prior execution authorization.
11. Any newly admitted remediation must enter the existing execution-plan and signed-request authorization path.
12. The debugger and adapter must remain independently testable and provider-neutral so they can later support other HOARE verticals.

## Relationship to SHELF-SCOUTER

The debugger and remediation adapter can inspect and re-enter the existing server-side pick workflow, including trusted evidence, admission, execution telemetry, signed execution requests, authorization, and receipts. They do not replace or modify the existing executor.
