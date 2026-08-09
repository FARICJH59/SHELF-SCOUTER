"""Event bridge for SHELF-SCOUTER -> EMQX -> HOARE/AEGIS/QGPS."""
from __future__ import annotations

import json
import logging
import os
import ssl
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

import requests

logger = logging.getLogger("shelf-scouter.event-bridge")
SCHEMA_VERSION = "1.0"

@dataclass
class ProductObservation:
    name: str
    category: str = "unknown"
    quantity: int | None = None
    shelf_position: str = "unknown"
    label_text: str = ""
    confidence: str = "unknown"

@dataclass
class ShelfObservation:
    observation_id: str
    device_id: str | None
    store_id: str | None
    aisle: str | None
    shelf: str | None
    captured_at: str
    products: list[ProductObservation] = field(default_factory=list)
    shelf_summary: str = ""
    total_unique_products: int = 0
    model: str | None = None
    query: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def build_observation(result: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Normalize an existing /scan result into a versioned observation event."""
    context = context or {}
    products = [ProductObservation(
        name=p.get("name", "unknown"),
        category=p.get("category", "unknown"),
        quantity=p.get("quantity"),
        shelf_position=p.get("shelf_position", "unknown"),
        label_text=p.get("label_text", ""),
        confidence=p.get("confidence", "unknown"),
    ) for p in result.get("products", [])]
    observation = ShelfObservation(
        observation_id=context.get("observation_id", str(uuid.uuid4())),
        device_id=context.get("device_id"),
        store_id=context.get("store_id"),
        aisle=context.get("aisle"),
        shelf=context.get("shelf"),
        captured_at=context.get("captured_at", datetime.now(timezone.utc).isoformat()),
        products=products,
        shelf_summary=result.get("shelf_summary", ""),
        total_unique_products=result.get("total_unique_products", len(products)),
        model=result.get("model"),
        query=context.get("query"),
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "event_type": "shelf.observation.created",
        "event_id": str(uuid.uuid4()),
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "observation": observation.to_dict(),
    }

class HttpControlPlane:
    """Optional HTTP bridge to HOARE, AEGIS and QGPS ingress endpoints."""
    def __init__(self) -> None:
        self.hoare_url = os.getenv("HOARE_EVENT_URL", "").rstrip("/")
        self.aegis_url = os.getenv("AEGIS_EVENT_URL", "").rstrip("/")
        self.qgps_url = os.getenv("QGPS_TELEMETRY_URL", "").rstrip("/")
        self.token = os.getenv("CONTROL_PLANE_TOKEN", "")
        self.timeout = float(os.getenv("CONTROL_PLANE_TIMEOUT", "5"))

    def _post(self, url: str, payload: dict[str, Any]) -> bool:
        if not url:
            return False
        headers = {"Content-Type": "application/json", "X-Schema-Version": SCHEMA_VERSION}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            return True
        except requests.RequestException:
            logger.exception("Control-plane delivery failed: %s", url)
            return False

    def send_to_hoare(self, event: dict[str, Any]) -> bool:
        return self._post(self.hoare_url, event)

    def send_to_aegis(self, event: dict[str, Any]) -> bool:
        return self._post(self.aegis_url, event)

    def send_to_qgps(self, event: dict[str, Any]) -> bool:
        telemetry = {
            "schema_version": SCHEMA_VERSION,
            "event_type": "shelf.inference.telemetry",
            "event_id": event["event_id"],
            "occurred_at": event["occurred_at"],
            "source": "shelf-scouter",
            "device_id": event["observation"].get("device_id"),
            "model": event["observation"].get("model"),
            "product_count": len(event["observation"].get("products", [])),
        }
        return self._post(self.qgps_url, telemetry)

class EmqxPublisher:
    """MQTT publisher for EMQX with TLS, QoS 1 and bounded retries."""
    def __init__(self) -> None:
        self.host = os.getenv("EMQX_HOST", "")
        self.port = int(os.getenv("EMQX_PORT", "8883"))
        self.username = os.getenv("EMQX_USERNAME", "")
        self.password = os.getenv("EMQX_PASSWORD", "")
        self.topic_prefix = os.getenv("EMQX_TOPIC_PREFIX", "shelf")
        self.client_id = os.getenv("EMQX_CLIENT_ID", f"shelf-scouter-{uuid.uuid4().hex[:12]}")
        self.tls = os.getenv("EMQX_TLS", "true").lower() == "true"
        self.retries = max(1, int(os.getenv("EMQX_RETRIES", "3")))

    def publish_observation(self, event: dict[str, Any]) -> bool:
        if not self.host:
            logger.info("EMQX_HOST not configured; skipping MQTT delivery")
            return False
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            logger.error("paho-mqtt is required for EMQX publishing")
            return False
        obs = event["observation"]
        topic = f"{self.topic_prefix}/{obs.get('store_id') or 'unknown-store'}/{obs.get('aisle') or 'unknown-aisle'}/{obs.get('shelf') or 'unknown-shelf'}/observation"
        payload = json.dumps(event, separators=(",", ":"))
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.client_id)
        if self.username:
            client.username_pw_set(self.username, self.password)
        if self.tls:
            client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
        for attempt in range(self.retries):
            try:
                client.connect(self.host, self.port, keepalive=30)
                client.loop_start()
                info = client.publish(topic, payload, qos=1)
                info.wait_for_publish(timeout=5)
                client.loop_stop()
                client.disconnect()
                if info.rc == mqtt.MQTT_ERR_SUCCESS:
                    return True
            except Exception:
                logger.exception("EMQX publish attempt %d/%d failed", attempt + 1, self.retries)
                try:
                    client.loop_stop(); client.disconnect()
                except Exception:
                    pass
            time.sleep(0.25 * (attempt + 1))
        return False

def dispatch(result: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build and dispatch one observation; delivery status is explicit."""
    event = build_observation(result, context)
    control = HttpControlPlane()
    return {
        "event_id": event["event_id"],
        "observation_id": event["observation"]["observation_id"],
        "delivery": {
            "emqx": EmqxPublisher().publish_observation(event),
            "hoare": control.send_to_hoare(event),
            "aegis": control.send_to_aegis(event),
            "qgps": control.send_to_qgps(event),
        },
        "event": event,
    }
