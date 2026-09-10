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

A vision candidate is only an observation. A model-supplied SKU is not physical identity proof, even when the SKU exists in the authorized retailer catalog. Catalog existence establishes canonical metadata; it does not establish that the photographed object is that SKU.

The trusted evidence authority therefore requires an explicit server-side `physical_identity_verified` result before issuing signed evidence. The current mobile gateway does not have an independent physical verifier, so `/verify` remains fail-closed to `UNKNOWN`/`409` rather than promoting model output to trusted identity.

A future trusted verifier can be a server-derived barcode decoder plus authorized catalog lookup, or an independently verified visual/physical identity service. Client-supplied barcode fields must remain observations unless independently re-derived on the server.

## Evidence binding

When trusted evidence exists, it is bound to both `session_id` and `frame_id`, signed by the server-side authority, and checked for expiry before HOARE admission. Evidence cannot be transferred to another session or source frame without invalidating the binding/signature.

## Barcode fast path

The fast-path module supports barcode observations, but the gateway must not treat a client-provided barcode as a trusted server-side barcode decode. A future server-side decoder can populate a trusted barcode observation and safely enable barcode-first routing.

## Telemetry

`latencyMs` is the individual execution measurement. `latencyP95Ms` must represent an aggregate P95 over a defined window and must not be populated from a single execution.
