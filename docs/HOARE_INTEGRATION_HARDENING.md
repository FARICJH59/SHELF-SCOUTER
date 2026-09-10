# HOARE Integration Hardening

**Design record:** 2026-09-10

## Trust boundary

The phone is an untrusted observation source. It must never receive `HOARE_INTERNAL_ROUTE_TOKEN` and must never create trusted product evidence.

Trusted sequence:

`PHONE → MOBILE GATEWAY → AUTHORIZED RETAILER ADAPTER → TRUSTED PRODUCT EVIDENCE → HOARE ADMISSION → EXECUTION`

## Resource routing

Production resource routing is supplied by a trusted server-side HOARE orchestrator. The mobile client does not submit an authoritative route decision.

For standalone development, `HOARE_SERVER_ROUTE_DECISION` may provide a server-side route decision. Its default is `ESCALATE`; it is not a replacement for the production HOARE resource router.

## Product identity

A vision candidate is only an observation until the authorized retailer adapter establishes the canonical SKU. Client barcode data remains an observation and cannot by itself create trusted evidence.

The `/verify` endpoint persists signed evidence on the source frame. Admission reconstructs and verifies that evidence before permitting `ALLOW`.

## Barcode fast path

The fast-path module supports barcode observations, but the gateway must not treat a client-provided barcode as a trusted server-side barcode decode. A future server-side decoder can populate the barcode observation and safely enable barcode-first routing.

## Telemetry

`latencyMs` is the individual execution measurement. `latencyP95Ms` must represent an aggregate P95 over a defined window and must not be populated from a single execution.
