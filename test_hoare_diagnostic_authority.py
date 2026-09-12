"""Governed Diagnostic Authority regression tests.

Design/provenance record: 2026-09-12.

These tests establish that diagnostic recovery is bounded and cannot silently
become action authority or trusted evidence.
"""

from hoare_diagnostic_authority import (
    DiagnosticAction,
    DiagnosticDecision,
    DiagnosticLease,
    DiagnosticLeaseController,
    DiagnosticObservation,
    RecoveryStep,
    assess_evidence,
    build_recovery_plan,
    diagnose,
)


def _controller():
    return DiagnosticLeaseController(
        DiagnosticLease(
            lease_id="gda-test-lease",
            allowed_actions=frozenset({
                DiagnosticAction.IMAGE_RESIZE,
                DiagnosticAction.IMAGE_ROTATE,
                DiagnosticAction.BARCODE_SCAN,
                DiagnosticAction.OCR,
                DiagnosticAction.REQUEST_RECAPTURE,
            }),
            max_attempts=3,
            max_duration_seconds=30,
            max_recovery_depth=3,
            max_compute_budget=2.0,
        ),
        started_at=0.0,
    )


def test_barcode_failure_can_create_bounded_recovery_plan():
    observation = DiagnosticObservation(
        session_id="session-1",
        source_frame_id="frame-1",
        failure_code="BARCODE_NOT_FOUND",
        confidence=0.95,
        facts={"rationale": "image is usable but no barcode was decoded"},
    )
    diagnosis = diagnose(observation)
    plan = build_recovery_plan(
        diagnosis,
        [
            RecoveryStep(DiagnosticAction.IMAGE_RESIZE, {"scale": 2}),
            RecoveryStep(DiagnosticAction.IMAGE_ROTATE, {"angles": [90, 180, 270]}),
            RecoveryStep(DiagnosticAction.BARCODE_SCAN),
        ],
        rationale="recover barcode evidence before vision fallback",
    )

    admission = _controller().admit(plan, compute_cost=1.0)

    assert diagnosis.failure_code == "BARCODE_NOT_FOUND"
    assert admission.decision is DiagnosticDecision.ALLOW
    assert admission.reasons == ("bounded_diagnostic_recovery",)


def test_unpermitted_action_is_denied():
    observation = DiagnosticObservation("s", "f", "VISION_FAILURE", 0.9)
    plan = build_recovery_plan(
        diagnose(observation),
        [RecoveryStep(DiagnosticAction.VISION_RETRY)],
        rationale="retry vision",
    )

    admission = _controller().admit(plan)

    assert admission.decision is DiagnosticDecision.DENY
    assert admission.reasons == ("diagnostic_action_not_permitted:VISION_RETRY",)


def test_attempt_limit_escalates_instead_of_looping_forever():
    controller = _controller()
    observation = DiagnosticObservation("s", "f", "BARCODE_NOT_FOUND", 0.9)
    plan = build_recovery_plan(
        diagnose(observation),
        [RecoveryStep(DiagnosticAction.BARCODE_SCAN)],
        rationale="retry barcode",
    )

    for _ in range(3):
        assert controller.admit(plan).decision is DiagnosticDecision.ALLOW

    admission = controller.admit(plan)

    assert admission.decision is DiagnosticDecision.ESCALATE
    assert admission.reasons == ("diagnostic_attempt_limit_reached",)


def test_compute_budget_escalates():
    controller = _controller()
    observation = DiagnosticObservation("s", "f", "IMAGE_QUALITY_FAILURE", 0.9)
    plan = build_recovery_plan(
        diagnose(observation),
        [RecoveryStep(DiagnosticAction.IMAGE_RESIZE)],
        rationale="improve image evidence",
    )

    admission = controller.admit(plan, compute_cost=2.1)

    assert admission.decision is DiagnosticDecision.ESCALATE
    assert admission.reasons == ("diagnostic_compute_budget_exceeded",)


def test_evidence_assessment_does_not_create_identity():
    assessment = assess_evidence(
        verified=False,
        facts={"barcode": None, "vision_candidate": "SKU-1"},
        reason="physical_identity_not_verified",
    )

    assert assessment.verified is False
    assert assessment.facts["vision_candidate"] == "SKU-1"
    assert assessment.reason == "physical_identity_not_verified"
