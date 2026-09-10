# HOARE Integration Hardening

**Design record:** 2026-09-10
**Hardening update:** 2026-09-10T23:00Z

## Trust boundary

The phone is an untrusted observation source. It must never receive `HOARE_INTERNAL_ROUTE_TOKEN` and must never create trusted product evidence.

Trusted sequence:

`PHONE → MOBILE GATEWAY → SERVER-SIDE PHYSICAL IDENTITY → AUTHORIZED RETAILER ADAPTER → TRUSTED PRODUCT EVIDENCE → HOARE ADMISSION → EXECUTION`

## Resource routing

Production resource routing is supplied by a trusted server-side HOARE orchestrator. The mobile client does not submit an authoritative route decision.

For standalone development, `HOARE_SERVER_ROUTE_DECISION` may provide a server-side route decision. Its default is `ESCALATE`; it is not a replacement for the production HOARE resource router.

## Product identity

A vision candidate is only an observation. A model-supplied SKU is not physical identity proof, even when the SKU exists in the authorized retailer catalog. Catalog existence establishes canonical metadata; it does not establish that the photographed object is that SKU.

The trusted evidence authority therefore requires an explicit server-side `physical_identity_verified` result before issuing signed evidence. The mobile gateway must not promote a client barcode, model SKU, OCR result, or catalog lookup into physical identity.

The physical identity boundary now includes an injectable server-side barcode verifier. It consumes server-controlled image bytes and accepts identity only when a real decoder returns a barcode that exactly matches the authorized expected GTIN after strict GTIN normalization. Decoder failures, malformed output, missing image bytes, and missing expected GTIN fail closed.

The verifier intentionally has no permissive default decoder. A deployment must supply a real barcode decoder/library or an independently validated physical-identity service. This prevents a missing dependency from becoming an authorization bypass.

## Server-controlled image handling

The server receives and decodes the image during `/frames`. A future production integration must perform physical identity verification against those server-controlled bytes before they are discarded, then persist only the minimum trusted verification result needed for the frame. The client-provided barcode remains an observation and must never be substituted for the server decode.

## Evidence binding

When trusted evidence exists, it is bound to both `session_id` and `frame_id`, signed by the server-side authority, and checked for expiry before HOARE admission. Evidence cannot be transferred to another session or source frame without invalidating the binding/signature.

## Barcode fast path

The fast-path module supports barcode observations, but the gateway must not treat a client-provided barcode as a trusted server-side barcode decode. A real server-side decoder can populate a trusted barcode observation and safely enable barcode-first routing only after exact GTIN comparison against authorized catalog data.

## Telemetry

`latencyMs` is the individual execution measurement. `latencyP95Ms` must represent an aggregate P95 over a defined window and must not be populated from a single execution.
