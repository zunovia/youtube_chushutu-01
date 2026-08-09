"""Base yt-dlp options.

These pin down settings whose absence causes wrong behaviour rather than an
error, which is the kind that ships unnoticed.
"""

from __future__ import annotations

from app.services.extractor import _base_opts, _build_strategies


def test_noplaylist_is_set() -> None:
    """A playlist or Mix link must download one video, not the whole list.

    YouTube produces `watch?v=X&list=RDX` from a playlist click and from
    autoplay, and that URL is claimed by the playlist extractor. Without
    noplaylist, /api/info returns playlist metadata with no formats and a
    download fetches every entry in the list.
    """
    assert _base_opts()["noplaylist"] is True


def test_windows_filename_safety() -> None:
    """Japanese titles routinely contain characters Windows rejects."""
    opts = _base_opts()
    assert opts["windowsfilenames"] is True
    assert opts["trim_file_name"] == 120


def test_strategy_chain_tries_plain_before_cookies() -> None:
    """Reading the browser cookie store is intrusive; it must not be step one."""
    strategies = _build_strategies()
    first_cookie = next(i for i, s in enumerate(strategies) if s.cookies)
    assert first_cookie > 0
    assert strategies[0].player_client is None
    assert not strategies[0].cookies


def test_cookie_strategies_are_last() -> None:
    """Once cookies are in play, every later strategy should keep using them."""
    strategies = _build_strategies()
    seen_cookie = False
    for strategy in strategies:
        if strategy.cookies:
            seen_cookie = True
        elif seen_cookie:
            raise AssertionError("a cookie-less strategy runs after a cookie one")
