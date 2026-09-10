"""Provider-neutral fast path for SHELF-SCOUTER camera frames."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from io import BytesIO

from PIL import Image, ImageFilter, ImageStat


@dataclass
class ImageQuality:
    width: int
    height: int
    megapixels: float
    sharpness_score: float
    brightness_score: float
    usable: bool
    reasons: list[str] = field(default_factory=list)


@dataclass
class BarcodeObservation:
    value: str
    format: str = "unknown"
    confidence: float = 0.0


@dataclass
class OCRObservation:
    text: str
    confidence: float = 0.0
    region: dict | None = None


@dataclass
class FastPathResult:
    image_sha256: str
    original_size: tuple[int, int]
    normalized_size: tuple[int, int]
    quality: ImageQuality
    barcodes: list[BarcodeObservation] = field(default_factory=list)
    ocr: list[OCRObservation] = field(default_factory=list)
    regions: list[tuple[int, int, int, int]] = field(default_factory=list)


def sha256_image(image: Image.Image) -> str:
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=90)
    return hashlib.sha256(buffer.getvalue()).hexdigest()


def estimate_sharpness(image: Image.Image) -> float:
    gray = image.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    return float(ImageStat.Stat(edges).var[0])


def estimate_brightness(image: Image.Image) -> float:
    return float(ImageStat.Stat(image.convert("L")).mean[0])


def inspect_image(image: Image.Image, min_sharpness: float = 5.0,
                  min_brightness: float = 25.0, max_brightness: float = 245.0) -> ImageQuality:
    width, height = image.size
    sharpness = estimate_sharpness(image)
    brightness = estimate_brightness(image)
    reasons: list[str] = []
    if sharpness < min_sharpness:
        reasons.append("sharpness_below_threshold")
    if brightness < min_brightness:
        reasons.append("brightness_too_low")
    if brightness > max_brightness:
        reasons.append("brightness_too_high")
    return ImageQuality(width, height, (width * height) / 1_000_000,
                        sharpness, brightness, not reasons, reasons)


def normalize_image(image: Image.Image, max_width: int = 960, max_height: int = 720) -> Image.Image:
    normalized = image.convert("RGB").copy()
    normalized.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
    return normalized


def generate_regions(image: Image.Image, rows: int = 3, columns: int = 3) -> list[tuple[int, int, int, int]]:
    width, height = image.size
    regions = []
    for row in range(rows):
        for col in range(columns):
            x0 = col * width // columns
            y0 = row * height // rows
            x1 = (col + 1) * width // columns
            y1 = (row + 1) * height // rows
            regions.append((x0, y0, x1, y1))
    return regions


def build_fast_path(image: Image.Image) -> FastPathResult:
    quality = inspect_image(image)
    normalized = normalize_image(image)
    return FastPathResult(
        image_sha256=sha256_image(image),
        original_size=image.size,
        normalized_size=normalized.size,
        quality=quality,
        regions=generate_regions(normalized),
    )


def add_barcode(result: FastPathResult, value: str, format: str = "unknown", confidence: float = 1.0) -> FastPathResult:
    result.barcodes.append(BarcodeObservation(value, format, confidence))
    return result


def add_ocr(result: FastPathResult, text: str, confidence: float = 1.0, region: dict | None = None) -> FastPathResult:
    result.ocr.append(OCRObservation(text, confidence, region))
    return result


def route_fast_path(result: FastPathResult) -> str:
    if result.barcodes:
        return "BARCODE_FAST"
    if result.ocr:
        return "OCR_TARGETED"
    if result.quality.usable:
        return "VISION_TARGETED"
    return "VISION_ESCALATION"
