"""Error classification tests.

These pin down the pattern ordering, which is the fragile part: several yt-dlp
messages match more than one rule, and the wrong winner sends the user down the
wrong remedy.
"""

from __future__ import annotations

import pytest

from app.services.errors import ACTION_UPDATE, ErrorCode, classify

CASES = [
    # ffmpeg — the failure that only appears at download time, because info
    # extraction never needs to merge anything.
    ("You have requested merging of multiple formats but ffmpeg is not installed", ErrorCode.FFMPEG_MISSING),
    ("ERROR: Postprocessing: ffmpeg not found", ErrorCode.FFMPEG_MISSING),
    ("ERROR: ffprobe is not installed", ErrorCode.FFMPEG_MISSING),

    ("ERROR: [youtube] abc: Sign in to confirm you're not a bot", ErrorCode.BOT_CHECK),
    # Must beat BOT_CHECK even though both mention "Sign in to confirm".
    ("ERROR: [youtube] abc: Sign in to confirm your age", ErrorCode.AGE_RESTRICTED),

    ("WARNING: [youtube] nsig extraction failed: Some formats may be missing", ErrorCode.OUTDATED_YTDLP),
    ("ERROR: Unable to extract player version", ErrorCode.OUTDATED_YTDLP),
    ("ERROR: unable to download video data: HTTP Error 403: Forbidden", ErrorCode.HTTP_FORBIDDEN),

    ("ERROR: [youtube] abc: Private video. Sign in if you've been granted access", ErrorCode.PRIVATE_VIDEO),
    ("ERROR: [youtube] abc: Join this channel to get access", ErrorCode.PRIVATE_VIDEO),
    # Must beat UNAVAILABLE — both phrases appear in the same message.
    ("ERROR: [youtube] abc: Video unavailable. This video is not available in your country", ErrorCode.GEO_BLOCKED),
    ("ERROR: [youtube] abc: Video unavailable", ErrorCode.UNAVAILABLE),
    ("ERROR: [youtube] abc: This live event will begin in 2 hours", ErrorCode.LIVE_NOT_ENDED),

    ("ERROR: Requested format is not available", ErrorCode.FORMAT_UNAVAILABLE),
    ("ERROR: could not find chrome cookies database in /root/.config/google-chrome", ErrorCode.COOKIE_LOCKED),
    ("ERROR: Failed to decrypt with DPAPI", ErrorCode.COOKIE_LOCKED),
    ("ERROR: Unable to download webpage: timed out", ErrorCode.NETWORK),
    ("ERROR: [Errno 28] No space left on device", ErrorCode.DISK_ERROR),
    ("ERROR: something nobody has seen before", ErrorCode.UNKNOWN),
]


@pytest.mark.parametrize("message,expected", CASES, ids=[c[1].value + ":" + c[0][:28] for c in CASES])
def test_classification(message: str, expected: ErrorCode) -> None:
    assert classify(message).code is expected


def test_every_code_has_a_message_and_remedy() -> None:
    """A code with no remedy would leave the user with nothing to act on."""
    for code in ErrorCode:
        result = classify(f"synthetic {code.value}")
        # classify() reaches every entry via the table, so look each up directly.
        from app.services.errors import _MESSAGES  # noqa: PLC0415

        message, remedy, _action = _MESSAGES[code]
        assert message.strip(), f"{code} has no message"
        assert remedy.strip(), f"{code} has no remedy"
        assert result is not None


def test_stale_ytdlp_offers_the_update_button() -> None:
    """The 'came back after months' failure must lead straight to the fix."""
    for message in (
        "ERROR: unable to download video data: HTTP Error 403: Forbidden",
        "WARNING: [youtube] nsig extraction failed",
    ):
        assert classify(message).action == ACTION_UPDATE


def test_type_based_classification() -> None:
    """Some failures never carry a yt-dlp message."""
    assert classify(TimeoutError("timed out")).code is ErrorCode.NETWORK
    assert classify(OSError(28, "No space left on device")).code is ErrorCode.DISK_ERROR


def test_noise_is_stripped_from_raw() -> None:
    assert not classify("ERROR: Video unavailable").raw.startswith("ERROR")
