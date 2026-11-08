"""Per-site URL handling.

Vimeo refuses anonymous requests on the vimeo.com page route even for public
videos, so every shape of Vimeo URL a user can be on must be rewritten to the
embed player. Getting this wrong fails silently into a "login required" error
for a video anyone can watch.
"""

from __future__ import annotations

import pytest

from app.services.errors import ErrorCode, classify
from app.services.extractor import (
    SITE_OTHER,
    SITE_VIMEO,
    SITE_YOUTUBE,
    Extractor,
    ExtractionError,
    _build_strategies,
    resolve_target,
)

PLAYER = "https://player.vimeo.com/video/76979871"


@pytest.mark.parametrize(
    "url",
    [
        "https://vimeo.com/76979871",
        "https://vimeo.com/76979871/",
        "https://vimeo.com/76979871?share=copy",
        "https://vimeo.com/channels/staffpicks/76979871",
        "https://vimeo.com/groups/name/videos/76979871",
        "https://vimeo.com/showcase/12345/video/76979871",
    ],
)
def test_vimeo_page_urls_become_the_player_url(url: str) -> None:
    target = resolve_target(url)
    assert target.site == SITE_VIMEO
    assert target.url == PLAYER
    assert target.opts["http_headers"]["Referer"] == "https://vimeo.com/"


def test_unlisted_hash_is_carried_over() -> None:
    assert resolve_target("https://vimeo.com/76979871/abcdef1234").url == PLAYER + "?h=abcdef1234"


def test_player_url_is_kept_but_gets_the_referer() -> None:
    target = resolve_target(PLAYER)
    assert target.url == PLAYER
    assert "Referer" in target.opts["http_headers"]


def test_vimeo_non_video_page_is_left_alone() -> None:
    """vimeo.com/home is the user's feed, not a video."""
    target = resolve_target("https://vimeo.com/home")
    assert target.site == SITE_VIMEO
    assert target.url == "https://vimeo.com/home"
    assert target.opts == {}


@pytest.mark.parametrize(
    "url", ["https://www.youtube.com/watch?v=abc&list=RDabc", "https://youtu.be/abc", "https://m.youtube.com/watch?v=abc"]
)
def test_youtube_urls_are_untouched(url: str) -> None:
    target = resolve_target(url)
    assert target.site == SITE_YOUTUBE
    assert target.url == url
    assert target.opts == {}


def test_other_sites_are_untouched() -> None:
    assert resolve_target("https://example.com/video/12345").site == SITE_OTHER


def test_vimeo_gets_a_single_attempt_without_cookies() -> None:
    """Public videos only: no YouTube clients to cycle, and never the browser's cookies."""
    strategies = _build_strategies(SITE_VIMEO)
    assert len(strategies) == 1
    assert not strategies[0].cookies
    assert strategies[0].player_client is None


@pytest.mark.parametrize(
    "message",
    [
        "ERROR: [vimeo] 1: The web client only works when logged-in. Use --cookies, --cookies-from-browser",
        "ERROR: [vimeo] 1: This video is protected by a password, use the --video-password option",
    ],
)
def test_vimeo_non_public_errors_say_so(message: str) -> None:
    error = classify(message)
    assert error.code is ErrorCode.PRIVATE_VIDEO
    assert error.action == "", "no 'YouTubeを開く' button under a Vimeo error"


def test_vimeo_403_is_not_blamed_on_the_js_runtime() -> None:
    """The Deno requirement is YouTube's; a Vimeo 403 must keep its own code."""
    extractor = Extractor()
    extractor._js_runtime = None
    calls = []

    def run(opts):
        calls.append(opts)
        raise RuntimeError("HTTP Error 403: Forbidden")

    with pytest.raises(ExtractionError) as excinfo:
        extractor._run_with_fallback(run, context="test", target=resolve_target("https://vimeo.com/76979871"))

    assert excinfo.value.classified.code is ErrorCode.HTTP_FORBIDDEN
    assert len(calls) == 1
    assert calls[0]["http_headers"]["Referer"] == "https://vimeo.com/"


@pytest.mark.parametrize(
    "message,expected",
    [
        # Seen for real on Vimeo's own demo video: every HLS playlist was under /drm/.
        ("ERROR: This format is DRM protected; Try selecting another format with --format", ErrorCode.DRM_PROTECTED),
        # The player answers 401 for videos that are not public or not embeddable.
        ("ERROR: [vimeo] 1084537: Unable to download webpage: HTTP Error 401: Unauthorized", ErrorCode.PRIVATE_VIDEO),
        ("ERROR: [vimeo] 347119375: Unable to download webpage: HTTP Error 404: Not Found", ErrorCode.UNAVAILABLE),
    ],
)
def test_real_vimeo_failures_get_real_reasons(message: str, expected: ErrorCode) -> None:
    """These used to fall through to UNKNOWN or NETWORK ("check your connection")."""
    assert classify(message).code is expected


# --- Audio intermediate must never collide with the saved video ----------------


def test_audio_name_is_finalized(tmp_path) -> None:
    from app.services.extractor import _finalize_audio_name

    produced = tmp_path / "The Mountain.ytc-audio.mp3"
    produced.write_bytes(b"x")
    assert _finalize_audio_name(produced) == tmp_path / "The Mountain.mp3"
    assert (tmp_path / "The Mountain.mp3").exists()


def test_audio_only_mp4_is_named_m4a_and_does_not_clobber_the_video(tmp_path) -> None:
    """Vimeo without ffmpeg: the audio arrives as .mp4, next to the real video."""
    from app.services.extractor import _finalize_audio_name

    video = tmp_path / "The Mountain.mp4"
    video.write_bytes(b"video")
    produced = tmp_path / "The Mountain.ytc-audio.mp4"
    produced.write_bytes(b"audio")

    final = _finalize_audio_name(produced)

    assert final == tmp_path / "The Mountain.m4a"
    assert video.read_bytes() == b"video"


def test_existing_audio_is_not_overwritten(tmp_path) -> None:
    from app.services.extractor import _finalize_audio_name

    (tmp_path / "Clip.mp3").write_bytes(b"first")
    produced = tmp_path / "Clip.ytc-audio.mp3"
    produced.write_bytes(b"second")

    final = _finalize_audio_name(produced)

    assert final == tmp_path / "Clip (2).mp3"
    assert (tmp_path / "Clip.mp3").read_bytes() == b"first"
