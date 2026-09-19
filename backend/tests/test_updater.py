"""Update checking.

The update button is this project's whole recovery story for "it worked months
ago and now it doesn't", so the check must never be the thing that breaks.
"""

from __future__ import annotations

import json

import pytest

from app.services import updater


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(updater.settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(updater, "_memo", None)
    # The runtime check shells out to whatever is installed on this machine;
    # tests of the version logic must not depend on that.
    from app.services.extractor import JsRuntime  # noqa: PLC0415

    monkeypatch.setattr(
        updater, "detect_js_runtime", lambda: JsRuntime(name="deno", path="/x/deno", version="2.9.7")
    )
    yield


def test_version_comparison() -> None:
    assert updater._is_newer("2026.07.04", "2026.03.17")
    assert updater._is_newer("2026.7.20", "2025.01.15")
    assert not updater._is_newer("2026.7.4", "2026.07.04")  # same version, padded
    assert updater._is_newer("2026.03.17.232145", "2026.03.17")  # nightly build


def test_version_comparison_survives_garbage() -> None:
    """A malformed version must not take the whole check down."""
    assert updater._parse_version("abc") == (0,)
    assert updater._parse_version("") == (0,)
    assert not updater._is_newer("abc", "2026.07.04")


@pytest.mark.parametrize("payload", ["[1, 2]", '"a string"', "42", "null"])
def test_cache_of_the_wrong_shape_is_ignored(payload: str) -> None:
    """Valid JSON that is not an object used to crash the endpoint with a 500.

    A list or string is truthy, so it slipped past the exception guard and then
    failed on .get() — silently killing update notifications for good.
    """
    path = updater._cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    assert updater._read_cache() is None


def test_corrupt_cache_is_ignored() -> None:
    path = updater._cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert updater._read_cache() is None


def test_offline_check_reports_rather_than_raising(monkeypatch) -> None:
    """Being offline is normal and must never surface as an error."""
    monkeypatch.setattr(updater, "_fetch_latest", lambda: None)
    info = updater.check_for_update(force=True)
    assert info.update_available is False
    assert info.note  # explains that the check could not run


def test_cache_hit_skips_the_network(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(updater, "_fetch_latest", lambda: calls.append(1) or "2099.01.01")

    first = updater.check_for_update()
    assert len(calls) == 1
    assert first.update_available is True

    second = updater.check_for_update()
    assert len(calls) == 1, "second call should be served from cache"
    assert second.from_cache is True


def test_force_bypasses_the_cache(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(updater, "_fetch_latest", lambda: calls.append(1) or "2099.01.01")
    updater.check_for_update()
    updater.check_for_update(force=True)
    assert len(calls) == 2


def test_pip_timeout_is_reported_not_raised(monkeypatch) -> None:
    """A slow connection must produce a message, not an HTTP 500."""
    import subprocess

    def boom(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="pip", timeout=300)

    monkeypatch.setattr(updater.subprocess, "run", boom)
    info = updater.apply_update()
    assert "タイムアウト" in info.note
    assert info.restart_required is False


def test_pip_failure_with_no_output_still_explains(monkeypatch) -> None:
    """A signal-killed pip produces no output; the note must not end at a colon."""
    import subprocess

    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda *_a, **_k: subprocess.CompletedProcess(args=[], returncode=-9, stdout="", stderr=""),
    )
    info = updater.apply_update()
    assert not info.note.rstrip().endswith(":")
    assert "-9" in info.note


def test_cache_roundtrip() -> None:
    updater._write_cache({"latest": "2026.07.04", "checked_at": 1.0})
    assert json.loads(updater._cache_path().read_text())["latest"] == "2026.07.04"


# --- JavaScript runtime ------------------------------------------------------


def test_missing_runtime_is_reported_as_an_available_update(monkeypatch) -> None:
    """yt-dlp being current is not enough; the popup must still offer the button."""
    monkeypatch.setattr(updater, "detect_js_runtime", lambda: None)
    monkeypatch.setattr(updater, "_fetch_latest", lambda: updater.get_yt_dlp_version())

    info = updater.check_for_update(force=True)

    assert info.update_available is True
    assert info.js_runtime_missing is True
    assert "Deno" in info.note


def test_present_runtime_does_not_nag(monkeypatch) -> None:
    monkeypatch.setattr(updater, "_fetch_latest", lambda: updater.get_yt_dlp_version())
    info = updater.check_for_update(force=True)
    assert info.update_available is False
    assert info.js_runtime_missing is False


def test_apply_update_upgrades_the_solver_bundle_and_installs_the_runtime(monkeypatch) -> None:
    """A bare `pip install -U yt-dlp` would leave yt-dlp-ejs and Deno behind."""
    import subprocess

    calls: list[list[str]] = []

    def fake_run(args, **_kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(updater.subprocess, "run", fake_run)
    monkeypatch.setattr(updater, "_fetch_latest", lambda: "2099.01.01")

    info = updater.apply_update()

    targets = [args[-1] for args in calls]
    assert targets == [updater.PIP_TARGET, updater.PIP_RUNTIME]
    assert targets[0].startswith("yt-dlp[default]")
    assert info.restart_required is True
    assert info.js_runtime_missing is False


def test_runtime_install_failure_is_explained_not_hidden(monkeypatch) -> None:
    """No Deno wheel for this machine: yt-dlp is upgraded, and the note says what is left."""
    import subprocess

    def fake_run(args, **_kwargs):
        failed = args[-1] == updater.PIP_RUNTIME
        return subprocess.CompletedProcess(
            args=args, returncode=1 if failed else 0, stdout="", stderr="No matching distribution found for deno"
        )

    monkeypatch.setattr(updater.subprocess, "run", fake_run)
    monkeypatch.setattr(updater, "_fetch_latest", lambda: "2099.01.01")
    monkeypatch.setattr(updater, "detect_js_runtime", lambda: None)

    info = updater.apply_update()

    assert info.restart_required is True, "the yt-dlp upgrade itself succeeded"
    assert info.js_runtime_missing is True
    assert "Deno" in info.note and "Node.js" in info.note
