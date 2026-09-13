"""Governed server-side barcode recovery for SHELF-SCOUTER.

GDA recovery is diagnostic authority only.

A recovered barcode MUST still pass:

    server-side evidence
        -> retailer adapter authorization
        -> trusted evidence
        -> HOARE admission

This module never authorizes a pick.

The recovery implementation is deliberately resource-bounded:
- server-controlled image bytes only
- bounded image dimensions
- bounded preprocessing variants
- bounded attempts
- hard wall-clock diagnostic budget
- no full-resolution upscaling
- no authorization decision
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import time

from PIL import Image, ImageEnhance, ImageOps

from hoare_diagnostic_authority import (
    DiagnosticAction,
    DiagnosticDecision,
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
    """Bounded server-side barcode recovery.

    Recovery is deliberately conservative:

    - server-controlled image bytes only
    - bounded image dimensions
    - bounded number of attempts
    - bounded wall-clock diagnostic budget
    - bounded preprocessing
    - no authorization decision

    Diagnostic success is never authorization.
    """

    MAX_IMAGE_DIMENSION = 1280
    MAX_DIAGNOSTIC_SECONDS = 5.0
    MAX_VARIANTS = 3
    JPEG_QUALITY = 82

    def __init__(self, decoder=None):
        self.decoder = decoder or PyzbarBarcodeDecoder()

        self.lease = DiagnosticLease(
            lease_id="shelf-scouter-barcode-recovery",
            allowed_actions=frozenset(
                {
                    DiagnosticAction.IMAGE_RESIZE,
                    DiagnosticAction.IMAGE_ENHANCE,
                    DiagnosticAction.IMAGE_ROTATE,
                    DiagnosticAction.BARCODE_SCAN,
                }
            ),
            max_attempts=self.MAX_VARIANTS,
            max_duration_seconds=self.MAX_DIAGNOSTIC_SECONDS,
            max_recovery_depth=3,
            max_compute_budget=1.5,
        )

    def recover(
        self,
        image_bytes: bytes,
        *,
        session_id: str = "barcode-recovery",
        source_frame_id: str = "server-image",
    ) -> BarcodeRecoveryResult:

        if not image_bytes:
            return BarcodeRecoveryResult(
                values=(),
                attempts=0,
                diagnosis="EMPTY_IMAGE",
                route=DiagnosticDecision.ESCALATE.value,
            )

        try:
            image = Image.open(BytesIO(image_bytes)).convert("RGB")
            image.load()
        except Exception:
            return BarcodeRecoveryResult(
                values=(),
                attempts=0,
                diagnosis="INVALID_IMAGE",
                route=DiagnosticDecision.ESCALATE.value,
            )

        observation = DiagnosticObservation(
            session_id=session_id,
            source_frame_id=source_frame_id,
            failure_code="BARCODE_NOT_FOUND",
            confidence=0.95,
            facts={
                "rationale": (
                    "direct server barcode probe "
                    "returned no identity"
                )
            },
        )

        diagnosis = diagnose(observation)

        plan = build_recovery_plan(
            diagnosis,
            [
                RecoveryStep(
                    DiagnosticAction.IMAGE_RESIZE,
                    {"max_dimension": self.MAX_IMAGE_DIMENSION},
                ),
                RecoveryStep(
                    DiagnosticAction.IMAGE_ENHANCE,
                ),
                RecoveryStep(
                    DiagnosticAction.IMAGE_ROTATE,
                    {"angles": [90]},
                ),
                RecoveryStep(
                    DiagnosticAction.BARCODE_SCAN,
                ),
            ],
            rationale=(
                "recover physical barcode evidence "
                "using bounded server preprocessing"
            ),
        )

        controller = DiagnosticLeaseController(self.lease)

        admission = controller.admit(
            plan,
            compute_cost=1.0,
        )

        if admission.decision != DiagnosticDecision.ALLOW:
            return BarcodeRecoveryResult(
                values=(),
                attempts=0,
                diagnosis=diagnosis.failure_code,
                route=admission.decision.value,
            )

        started = time.perf_counter()

        # Never upscale a phone image for diagnostic recovery.
        # Downscale only when the source exceeds the hard diagnostic
        # dimension budget.
        bounded = image.copy()
        bounded.thumbnail(
            (
                self.MAX_IMAGE_DIMENSION,
                self.MAX_IMAGE_DIMENSION,
            ),
            Image.Resampling.LANCZOS,
        )

        contrast = ImageEnhance.Contrast(
            bounded
        ).enhance(1.35)

        sharp = ImageEnhance.Sharpness(
            contrast
        ).enhance(1.5)

        variants = [
            bounded,
            ImageOps.autocontrast(bounded),
            sharp,
        ]

        values: list[str] = []
        seen: set[str] = set()
        attempts = 0

        for variant in variants[: self.MAX_VARIANTS]:
            # Hard wall-clock budget. This is checked before every
            # diagnostic attempt so GDA cannot silently consume an
            # unbounded amount of tenant/device compute.
            if (
                time.perf_counter() - started
                >= self.MAX_DIAGNOSTIC_SECONDS
            ):
                return BarcodeRecoveryResult(
                    values=tuple(values),
                    attempts=attempts,
                    diagnosis="GDA_COMPUTE_BUDGET_EXHAUSTED",
                    route=DiagnosticDecision.ESCALATE.value,
                )

            if attempts >= self.lease.max_attempts:
                break

            attempts += 1
            buffer = BytesIO()

            try:
                # JPEG is deliberately used for bounded diagnostic
                # transport/encoding. The original implementation
                # generated expensive full PNG variants.
                variant.save(
                    buffer,
                    format="JPEG",
                    quality=self.JPEG_QUALITY,
                    optimize=False,
                )

                decoded = self.decoder.decode(
                    buffer.getvalue()
                )

            except Exception:
                decoded = []

            if not isinstance(decoded, list):
                continue

            for value in decoded:
                if not isinstance(value, str):
                    continue

                clean = value.strip()

                if not clean or clean in seen:
                    continue

                seen.add(clean)
                values.append(clean)

            if values:
                return BarcodeRecoveryResult(
                    values=tuple(values),
                    attempts=attempts,
                    diagnosis=diagnosis.failure_code,
                    route="BARCODE_RECOVERED",
                )

        elapsed = time.perf_counter() - started

        if elapsed >= self.MAX_DIAGNOSTIC_SECONDS:
            return BarcodeRecoveryResult(
                values=tuple(values),
                attempts=attempts,
                diagnosis="GDA_COMPUTE_BUDGET_EXHAUSTED",
                route=DiagnosticDecision.ESCALATE.value,
            )

        return BarcodeRecoveryResult(
            values=tuple(values),
            attempts=attempts,
            diagnosis=diagnosis.failure_code,
            route=DiagnosticDecision.ESCALATE.value,
        )


__all__ = [
    "BarcodeRecoveryResult",
    "GovernedBarcodeRecovery",
]
