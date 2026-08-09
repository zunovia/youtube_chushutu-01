"""Retry chain behaviour.

The chain exists so a transient YouTube block does not become a dead end, but
it must not turn a permanent failure into a long wait — and it must report the
cause that actually explains the failure.
"""

from __future__ import annotations

import pytest

from app.services.errors import ClassifiedError, ErrorCode, classify
from app.services.extractor import Extractor, ExtractionError, _primary_error


def _run(extractor: Extractor, errors: list[str]):
    """Fail with the next message in `errors` on each successive attempt."""
    calls: list[dict] = []

    def run(opts: dict):
        index = len(calls)
        calls.append(opts)
        if index < len(errors):
            raise RuntimeError(errors[index])
        return "ok"

    return run, calls


def test_non_retryable_stops_after_one_attempt() -> None:
    extractor = Extractor()
    run, calls = _run(extractor, ["Private video"] * 10)

    with pytest.raises(ExtractionError) as excinfo:
        extractor._run_with_fallback(run, context="test")

    assert len(calls) == 1, "a private video fails the same way on every client"
    assert excinfo.value.classified.code is ErrorCode.PRIVATE_VIDEO


def test_retryable_walks_the_chain_then_reports() -> None:
    extractor = Extractor()
    run, calls = _run(extractor, ["Sign in to confirm you're not a bot"] * 10)

    with pytest.raises(ExtractionError) as excinfo:
        extractor._run_with_fallback(run, context="test")

    assert len(calls) > 1
    assert len(excinfo.value.attempts) == len(calls)
    assert excinfo.value.classified.code is ErrorCode.BOT_CHECK


def test_success_on_a_later_attempt() -> None:
    extractor = Extractor()
    run, calls = _run(extractor, ["HTTP Error 403: Forbidden"])
    seen: list[tuple[int, int, str]] = []

    result = extractor._run_with_fallback(run, context="test", on_attempt=lambda *a: seen.append(a))

    assert result == "ok"
    assert len(calls) == 2
    assert seen[0][0] == 1 and seen[1][0] == 2


def test_cookie_failure_does_not_mask_the_real_cause() -> None:
    """Four attempts said 403; the cookie store merely could not be opened.

    Reporting the last error would tell the user to fiddle with cookies when
    what they actually need is a yt-dlp update.
    """
    errors = [
        classify("HTTP Error 403: Forbidden"),
        classify("HTTP Error 403: Forbidden"),
        classify("could not find chrome cookies database"),
    ]
    assert _primary_error(errors).code is ErrorCode.HTTP_FORBIDDEN


def test_primary_error_falls_back_when_everything_is_infrastructure() -> None:
    errors = [classify("could not find chrome cookies database")]
    assert _primary_error(errors).code is ErrorCode.COOKIE_LOCKED


def test_primary_error_prefers_the_earliest_on_a_tie() -> None:
    errors: list[ClassifiedError] = [
        classify("Requested format is not available"),
        classify("Video unavailable"),
    ]
    assert _primary_error(errors).code is ErrorCode.FORMAT_UNAVAILABLE
