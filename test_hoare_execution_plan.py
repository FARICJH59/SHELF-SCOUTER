from hoare_execution_plan import (
    ExecutionPlanError,
    compile_execution_plan,
    verify_execution_plan,
)
from hoare_pick_admission import (
    AdmissionDecision,
    PickRequest,
    ResourceRoute,
    admit_pick,
)
from product_verification import (
    IdentityStatus,
    ProductIdentity,
)


def _allowed_admission():
    request = PickRequest(
        tenant_id="tenant-1",
        order_id="order-1",
        requested_sku="SKU-1",
        device_id="device-1",
    )

    identity = ProductIdentity(
        requested_sku="SKU-1",
        detected_sku="SKU-1",
        name="Test Product",
        status=IdentityStatus.VERIFIED,
        confidence=0.99,
    )

    route = ResourceRoute(
        decision=AdmissionDecision.ALLOW,
        provider="edge",
        region="edge-local",
        reason=["policy_ok"],
    )

    admission = admit_pick(
        request,
        identity,
        route,
    )

    assert admission.decision is AdmissionDecision.ALLOW

    return admission


def test_execution_plan_is_server_authoritative():
    admission = _allowed_admission()

    plan = compile_execution_plan(
        admission=admission,
        source_frame_id="frame-1",
        evidence_signature="trusted-evidence-signature",
        quantity=1,
        capability_version="1.0.0",
        contract_version="1.0.0",
    )

    assert plan.schema == "hoare.execution-plan.v1"
    assert plan.plan_version == "1.0.0"
    assert plan.operation == "SHELF_SCOUTER_PICK"
    assert plan.plan_hash
    assert verify_execution_plan(plan)


def test_execution_plan_hash_changes_when_target_changes():
    admission = _allowed_admission()

    first = compile_execution_plan(
        admission=admission,
        source_frame_id="frame-1",
        evidence_signature="evidence-a",
        quantity=1,
        capability_version="1.0.0",
        contract_version="1.0.0",
    )

    second = compile_execution_plan(
        admission=admission,
        source_frame_id="frame-2",
        evidence_signature="evidence-a",
        quantity=1,
        capability_version="1.0.0",
        contract_version="1.0.0",
    )

    assert first.plan_hash != second.plan_hash


def test_execution_plan_hash_changes_when_quantity_changes():
    admission = _allowed_admission()

    first = compile_execution_plan(
        admission=admission,
        source_frame_id="frame-1",
        evidence_signature="evidence-a",
        quantity=1,
        capability_version="1.0.0",
        contract_version="1.0.0",
    )

    second = compile_execution_plan(
        admission=admission,
        source_frame_id="frame-1",
        evidence_signature="evidence-a",
        quantity=2,
        capability_version="1.0.0",
        contract_version="1.0.0",
    )

    assert first.plan_hash != second.plan_hash


def test_execution_plan_hash_changes_when_evidence_changes():
    admission = _allowed_admission()

    first = compile_execution_plan(
        admission=admission,
        source_frame_id="frame-1",
        evidence_signature="evidence-a",
        quantity=1,
        capability_version="1.0.0",
        contract_version="1.0.0",
    )

    second = compile_execution_plan(
        admission=admission,
        source_frame_id="frame-1",
        evidence_signature="evidence-b",
        quantity=1,
        capability_version="1.0.0",
        contract_version="1.0.0",
    )

    assert first.plan_hash != second.plan_hash


def test_execution_plan_rejects_non_allow():
    request = PickRequest(
        tenant_id="tenant-1",
        order_id="order-1",
        requested_sku="SKU-1",
        device_id="device-1",
    )

    identity = ProductIdentity(
        requested_sku="SKU-1",
        detected_sku=None,
        name=None,
        status=IdentityStatus.UNKNOWN,
        confidence=0.0,
    )

    route = ResourceRoute(
        decision=AdmissionDecision.DENY,
        reason=["policy_denied"],
    )

    admission = admit_pick(
        request,
        identity,
        route,
        require_verified_identity=False,
    )

    assert admission.decision is AdmissionDecision.DENY

    try:
        compile_execution_plan(
            admission=admission,
            source_frame_id="frame-1",
            evidence_signature="evidence",
            quantity=1,
            capability_version="1.0.0",
            contract_version="1.0.0",
        )
    except ExecutionPlanError as exc:
        assert str(exc) == "execution_plan_requires_allow_admission"
    else:
        raise AssertionError(
            "DENY admission created an execution plan"
        )


def test_execution_plan_rejects_missing_source_frame():
    admission = _allowed_admission()

    try:
        compile_execution_plan(
            admission=admission,
            source_frame_id="",
            evidence_signature="evidence",
            quantity=1,
            capability_version="1.0.0",
            contract_version="1.0.0",
        )
    except ExecutionPlanError as exc:
        assert str(exc) == "execution_plan_source_frame_required"
    else:
        raise AssertionError(
            "Missing source frame created an execution plan"
        )


def test_execution_plan_rejects_missing_evidence():
    admission = _allowed_admission()

    try:
        compile_execution_plan(
            admission=admission,
            source_frame_id="frame-1",
            evidence_signature="",
            quantity=1,
            capability_version="1.0.0",
            contract_version="1.0.0",
        )
    except ExecutionPlanError as exc:
        assert str(exc) == "execution_plan_evidence_signature_required"
    else:
        raise AssertionError(
            "Missing evidence created an execution plan"
        )


def test_execution_plan_rejects_invalid_quantity():
    admission = _allowed_admission()

    try:
        compile_execution_plan(
            admission=admission,
            source_frame_id="frame-1",
            evidence_signature="evidence",
            quantity=0,
            capability_version="1.0.0",
            contract_version="1.0.0",
        )
    except ExecutionPlanError as exc:
        assert str(exc) == "execution_plan_quantity_invalid"
    else:
        raise AssertionError(
            "Invalid quantity created an execution plan"
        )


def test_execution_plan_rejects_unbound_route():
    admission = _allowed_admission()

    bad_route_admission = admission.__class__(
        decision=AdmissionDecision.ALLOW,
        reasons=admission.reasons,
        request=admission.request,
        identity_status=admission.identity_status,
        identity_confidence=admission.identity_confidence,
        resource_route=ResourceRoute(
            decision=AdmissionDecision.ALLOW,
            provider=None,
            region=None,
        ),
    )

    try:
        compile_execution_plan(
            admission=bad_route_admission,
            source_frame_id="frame-1",
            evidence_signature="evidence",
            quantity=1,
            capability_version="1.0.0",
            contract_version="1.0.0",
        )
    except ExecutionPlanError as exc:
        assert str(exc) == "execution_plan_target_unbound"
    else:
        raise AssertionError(
            "Unbound route created an execution plan"
        )


def test_execution_plan_tampering_is_detected():
    admission = _allowed_admission()

    plan = compile_execution_plan(
        admission=admission,
        source_frame_id="frame-1",
        evidence_signature="evidence-a",
        quantity=1,
        capability_version="1.0.0",
        contract_version="1.0.0",
    )

    assert verify_execution_plan(plan)

    tampered = plan.__class__(
        schema=plan.schema,
        plan_version=plan.plan_version,
        operation=plan.operation,
        tenant_id=plan.tenant_id,
        order_id=plan.order_id,
        device_id=plan.device_id,
        intent=plan.intent,
        requested_sku="SKU-TAMPERED",
        source_frame_id=plan.source_frame_id,
        evidence_signature=plan.evidence_signature,
        resource_provider=plan.resource_provider,
        resource_region=plan.resource_region,
        capability_version=plan.capability_version,
        contract_version=plan.contract_version,
        quantity=plan.quantity,
        plan_hash=plan.plan_hash,
    )

    assert not verify_execution_plan(tampered)
