from PIL import Image

from fast_path import build_fast_path, route_fast_path
from product_verification import IdentityStatus, verify_product
from hoare_pick_admission import AdmissionDecision, PickRequest, ResourceRoute, admit_pick
from execution_feedback import ExecutionFeedbackRecorder


def test_fast_path_quality_and_route():
    image = Image.new("RGB", (1280, 960), (120, 120, 120))
    result = build_fast_path(image)
    assert result.normalized_size == (960, 720)
    assert result.image_sha256
    assert route_fast_path(result) in {"VISION_ESCALATION", "VISION_TARGETED"}


def test_inferred_identity_escalates():
    identity = verify_product(name="Cheerios", visual_match=True)
    request = PickRequest("tenant", "order", "SKU-1", "phone")
    admission = admit_pick(request, identity)
    assert identity.status is IdentityStatus.INFERRED
    assert admission.decision is AdmissionDecision.ESCALATE


def test_verified_identity_allows():
    identity = verify_product(
        requested_sku="SKU-1", detected_sku="SKU-1",
        name="Cheerios", barcode_match=True, catalog_match=True, visual_match=True,
    )
    request = PickRequest("tenant", "order", "SKU-1", "phone")
    route = ResourceRoute(AdmissionDecision.ALLOW, provider="edge", region="edge-local")
    admission = admit_pick(request, identity, route)
    assert identity.status is IdentityStatus.VERIFIED
    assert admission.decision is AdmissionDecision.ALLOW


def test_resource_escalation_blocks_pick():
    identity = verify_product(requested_sku="SKU-1", detected_sku="SKU-1")
    request = PickRequest("tenant", "order", "SKU-1", "phone")
    route = ResourceRoute(AdmissionDecision.ESCALATE, reason=["latency_slo_not_met"])
    admission = admit_pick(request, identity, route, require_verified_identity=False)
    assert admission.decision is AdmissionDecision.ESCALATE


def test_execution_feedback():
    recorder = ExecutionFeedbackRecorder()
    execution = recorder.start(
        tenant_id="tenant", order_id="order", requested_sku="SKU-1",
        provider="edge", region="edge-local", device_id="phone", model="targeted-vision",
    )
    completed = recorder.complete(
        execution.execution_id, success=True,
        identity_status="VERIFIED", identity_confidence=0.99,
    )
    observation = recorder.telemetry_observation(completed.execution_id)
    assert completed.success is True
    assert completed.latency_ms is not None
    assert observation["source"] == "shelf-scouter-execution"
