# HOARE Integration Hardening

**Design record:** 2026-09-10
**Hardening update:** 2026-09-10T10:50Z

## Trust boundary

The phone is an untrusted observation source. It must never receive `HOARE_INTERNAL_ROUTE_TOKEN` and must never create trusted product evidence.

Trusted sequence:

`PHONE → MOBILE GATEWAY → SERVER-CONTROLLED IMAGE → SERVER BARCODE DECODER → AUTHORIZED RETAILER ADAPTER → TRUSTED PRODUCT EVIDENCE → HOARE ADMISSION → EXECUTION`

## Resource routing

Production resource routing is supplied by a trusted server-side HOARE orchestrator. The mobile client does not submit an authoritative route decision.

For standalone development, `HOARE_SERVER_ROUTE_DECISION` may provide a server-side route decision. Its default is `ESCALATE`; it is not a replacement for the production HOARE resource router.

## Product identity

A vision candidate is only an observation. A model-supplied SKU is not physical identity proof, even when the SKU exists in the authorized retailer catalog. Catalog existence establishes canonical metadata; it does not establish that the photographed object is that SKU.

The trusted evidence authority therefore requires an explicit server-side `physical_identity_verified` result before issuing signed evidence. The mobile gateway must not promote a client barcode, model SKU, OCR result, or catalog lookup into physical identity.

The physical identity boundary now includes a production `PyzbarBarcodeDecoder` backed by ZBar. The decoder consumes server-controlled image bytes and permits only retail barcode symbologies before the verifier compares the decoded value with the authorized expected GTIN. GTIN normalization is strict numeric normalization with check-digit validation. Decoder failures, malformed output, unsupported barcode types, missing image bytes, invalid GTINs, and missing expected GTIN fail closed.

The expected GTIN is obtained from an exact authorized retailer-adapter SKU lookup. The client-provided barcode is never used as the expected GTIN and never participates in the trust decision.

The Docker image installs the native `libzbar0` dependency required by pyzbar. The Python decoder import remains lazy so environments without ZBar, including constrained development environments, fail closed instead of silently authorizing physical identity.

## Server-controlled image handling

The server receives and decodes the image during `/frames`. The gateway performs physical identity verification against a lossless PNG serialization of that server-decoded image before the image is discarded. Only the boolean verification result and authorized GTIN are retained with the frame; raw image bytes are not persisted by this boundary.

## Evidence binding

When trusted evidence exists, it is bound to both `session_id` and `frame_id`, signed by the server-side authority, and checked for expiry before HOARE admission. Evidence cannot be transferred to another session or source frame without invalidating the binding/signature.

## Barcode fast path

The fast-path module supports barcode observations, but the gateway must not treat a client-provided barcode as a trusted server-side barcode decode. The server decoder operates independently on server-controlled image bytes. Barcode-first routing can only become trusted after exact GTIN comparison against authorized catalog data.

## Telemetry

`latencyMs` is the individual execution measurement. `latencyP95Ms` must represent an aggregate P95 over a defined window and must not be populated from a single execution.
