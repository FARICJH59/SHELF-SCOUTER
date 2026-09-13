from io import BytesIO

from PIL import Image

from hoare_diagnostic_barcode import (
    GovernedBarcodeRecovery,
)


class FakeDecoder:
    def __init__(self, values=None):
        self.values = values or []
        self.calls = 0

    def decode(self, image_bytes):
        self.calls += 1
        return list(self.values)


class FailDecoder:
    def __init__(self):
        self.calls = 0

    def decode(self, image_bytes):
        self.calls += 1
        raise RuntimeError("decoder failure")


def make_image_bytes():
    image = Image.new(
        "RGB",
        (100, 100),
        "white",
    )

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_empty_image_escalates_without_decoder():
    decoder = FakeDecoder(
        ["00012345678905"]
    )

    result = GovernedBarcodeRecovery(
        decoder
    ).recover(b"")

    assert result.values == ()
    assert result.attempts == 0
    assert result.route == "ESCALATE"
    assert decoder.calls == 0


def test_invalid_image_escalates():
    decoder = FakeDecoder(
        ["00012345678905"]
    )

    result = GovernedBarcodeRecovery(
        decoder
    ).recover(b"not-an-image")

    assert result.values == ()
    assert result.route == "ESCALATE"
    assert decoder.calls == 0


def test_recovery_returns_server_decoded_barcode():
    decoder = FakeDecoder(
        ["00012345678905"]
    )

    result = GovernedBarcodeRecovery(
        decoder
    ).recover(
        make_image_bytes(),
        session_id="session-1",
        source_frame_id="frame-1",
    )

    assert result.values == (
        "00012345678905",
    )
    assert result.route == "BARCODE_RECOVERED"
    assert result.attempts == 1
    assert decoder.calls == 1


def test_recovery_deduplicates_decoder_results():
    decoder = FakeDecoder(
        [
            "00012345678905",
            "00012345678905",
            " 00012345678905 ",
        ]
    )

    result = GovernedBarcodeRecovery(
        decoder
    ).recover(make_image_bytes())

    assert result.values == (
        "00012345678905",
    )


def test_decoder_failure_fails_closed():
    decoder = FailDecoder()

    result = GovernedBarcodeRecovery(
        decoder
    ).recover(make_image_bytes())

    assert result.values == ()
    assert result.route == "ESCALATE"
    assert result.attempts == GovernedBarcodeRecovery.MAX_VARIANTS
    assert decoder.calls == GovernedBarcodeRecovery.MAX_VARIANTS


def test_recovery_is_bounded():
    decoder = FakeDecoder()

    result = GovernedBarcodeRecovery(
        decoder
    ).recover(make_image_bytes())

    assert result.values == ()
    assert result.route == "ESCALATE"
    assert result.attempts <= 6
    assert decoder.calls <= 6
