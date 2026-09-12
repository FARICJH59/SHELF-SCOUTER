"""Governed barcode recovery for SHELF-SCOUTER.

Design/provenance record: 2026-09-12.

This module performs bounded, server-side barcode recovery after the direct
barcode probe fails. It never authorizes a pick and never treats a decoded
barcode as trusted identity until the caller performs the existing retailer
adapter authorization and physical-evidence checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from hoare_diagnostic_authority import (
    DiagnosticAction,
    DiagnosticLease,
    DiagnosticLeaseController,
    DiagnosticObservation,
    RecoveryStep,
    build_recovery_plan,
    diagnose,
)
from physical_identity_verifier import PyzbarBarcodeDecoder


@dataclass(frozen=True)
class BarcodeRecoveryResult:
    values: tuple[str, ...]
    attempts: int
    diagnosis: str
    route: str


class GovernedBarcodeRecovery:
    """Bounded preprocessing + server-side barcode recovery."""

    def __init__(self, decoder=None):
        self.decoder = decoder or PyzbarBarcodeDecoder()
        self.lease = DiagnosticLease(
            lease_id="shelf-scouter-barcode-recovery",
            allowed_actions=frozenset({
                DiagnosticAction.IMAGE_RESIZE,
                DiagnosticAction.IMAGE_ENHANCE,
                DiagnosticAction.IMAGE_ROTATE,
                DiagnosticAction.BARCODE_SCAN,
            }),
            max_attempts=3,
            max_duration_seconds=15.0,
            max_recovery_depth=3,
            max_compute_budget=1.5,
        )

    def recover(self, image_bytes: bytes) -> BarcodeRecoveryResult:
        if not image_bytes:
            return BarcodeRecoveryResult((), 0, "EMPTY_IMAGE", "ESCALATE")

        try:
            image = Image.open(BytesIO(image_bytes)).convert("RGB")
            image.load()
        except Exception:
            return BarcodeRecoveryResult((), 0, "INVALID_IMAGE", "ESCALATE")

        observation = DiagnosticObservation(
            session_id="barcode-recovery",
            source_frame_id="server-image",
            failure_code="BARCODE_NOT_FOUND",
            confidence=0.95,
            facts={"rationale": "direct server barcode probe returned no identity"},
        )
        diagnosis = diagnose(observation)
        plan = build_recovery_plan(
            diagnosis,
            [
                RecoveryStep(DiagnosticAction.IMAGE_RESIZE, {"scale": 2}),
                RecoveryStep(DiagnosticAction.IMAGE_ENHANCE),
                RecoveryStep(DiagnosticAction.IMAGE_ROTATE, {"angles": [90, 180, 270]}),
                RecoveryStep(DiagnosticAction.BARCODE_SCAN),
            ],
            rationale="recover physical barcode evidence using bounded server preprocessing",
        )

        controller = DiagnosticLeaseController(self.lease)
        admission = controller.admit(plan, compute_cost=1.0)
        if admission.decision.value != "ALLOW":
            return BarcodeRecoveryResult((), 0, diagnosis.failure_code, admission.decision.value)

        variants = [
            image,
            ImageOps.autocontrast(image),
            ImageEnhance.Contrast(image).enhance(1.8),
            ImageEnhance.Sharpness(ImageEnhance.Contrast(image).enhance(1.6)).enhance(2.0),
            image.resize((image.width * 2, image.height * 2)),
        ]

        rotated = image.resize((image.width * 2, image.height * 2))
        variants.extend(rotated.rotate(angle, expand=True) for angle in (90, 180, 270))

        values: list[str] = []
        seen: set[str] = set()
        attempts = 0

        for variant in variants:
            if attempts >= self.lease.max_attempts:
                break
            attempts += 1
            buffer = BytesIO()
            variant.save(buffer, format="PNG")
            try:
                decoded = self.decoder.decode(buffer.getvalue())
            except Exception:
                decoded = []
            for value in decoded if isinstance(decoded, list) else []:
                if isinstance(value, str) and value.strip() and value.strip() not in seen:
                    clean = value.strip()
                    seen.add(clean)
                    values.append(clean)

            if values:
                return BarcodeRecoveryResult(
                    tuple(values), attempts, diagnosis.failure_code, "BARCODE_RECOVERED"
                )

        return BarcodeRecoveryResult(
            tuple(values), attempts, diagnosis.failure_code, "ESCALATE"
        )
