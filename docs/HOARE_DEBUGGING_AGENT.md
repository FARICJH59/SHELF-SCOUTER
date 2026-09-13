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

## Safety rules

1. Client observations are never promoted to authority by diagnosis.
2. A missing trusted-evidence boundary is a critical condition.
3. Missing execution authorization is a critical condition.
4. Proposed actions are recommendations only.
5. Post-execution diagnosis cannot alter the already-completed execution result.
6. Diagnostic provenance is not execution authority and is not added to the signed request payload.
7. Any future remediation executor must enter the existing HOARE execution boundary and signed-request authorization path.
8. The debugger must remain independently testable and provider-neutral so it can later support other HOARE verticals.

## Relationship to SHELF-SCOUTER

The debugger can inspect the existing server-side pick workflow, including trusted evidence, admission, execution telemetry, signed execution requests, authorization, and receipts. It does not replace or modify the existing executor.
