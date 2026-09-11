# Shelf Scouter Control-Plane Integration

This enhancement adds a normalized event contract and an optional delivery bridge for EMQX, HOARE, AEGIS, and QGPS.

## Event flow

```text
Gemma scan result
      |
      v
build_observation()
      |
      +--> EMQX MQTT: shelf/{store}/{aisle}/{shelf}/observation
      +--> HOARE_EVENT_URL
      +--> AEGIS_EVENT_URL
      +--> QGPS_TELEMETRY_URL
```

The bridge is implemented in `shelf_event_bridge.py` and can be imported by the Flask service or another edge runtime.

## Normalized event

Every observation uses:

- `schema_version`
- `event_type=shelf.observation.created`
- `event_id`
- `occurred_at`
- `observation.observation_id`
- `device_id`, `store_id`, `aisle`, `shelf`
- product observations with quantity, position, label text, and confidence
- model and query context

## EMQX

Default topic:

```text
shelf/{store_id}/{aisle}/{shelf}/observation
```

The publisher uses TLS by default, QoS 1, configurable credentials, and bounded retries. Do not commit broker credentials; provide them through environment variables or a secret manager.

## HOARE

Set `HOARE_EVENT_URL` to the HOARE event-ingress endpoint. The complete normalized observation is forwarded with the schema version header.

HOARE can then persist the observation, update memory, correlate repeated shelf conditions, create incidents, and invoke its decision engine.

## AEGIS

Set `AEGIS_EVENT_URL` to the AEGIS observation/policy ingress endpoint. AEGIS receives the same event so authorization and evidence policy can be applied before any autonomous action is executed.

## QGPS

Set `QGPS_TELEMETRY_URL` to the QGPS telemetry endpoint. The bridge sends a reduced workload telemetry record containing model, device, event, and product-count information. This is intentionally separate from retail business data.

## Environment

See `.env.example`. Production deployments should inject credentials with a secret manager rather than storing them in `.env` files.

## Current implementation boundary

The bridge is deliberately added without hard-coding the deployment-specific HOARE, AEGIS, or QGPS URLs. The next integration step is to call `dispatch()` from the `/scan` and `/search` paths after a successful observation, then add the EMQX dead-letter/replay consumer and AEGIS action authorization flow.
