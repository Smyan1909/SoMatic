from __future__ import annotations

import json
import os
import sys

import pytest

from somatic import headless
from somatic.jsonio import SomaticError

linux_only = pytest.mark.skipif(sys.platform != "linux", reason="headless requires Linux")


def test_supported_platform_matches_runtime():
    assert headless.supported_platform() is (sys.platform == "linux")


def test_start_errors_on_non_linux(monkeypatch):
    monkeypatch.setattr(headless, "supported_platform", lambda: False)
    with pytest.raises(SomaticError) as exc:
        headless.start()
    assert exc.value.code == "headless_unsupported_platform"


def test_apply_active_env_no_op_when_disabled(monkeypatch, tmp_path):
    # The session-wide fixture sets this; just make sure the no-op is honoured
    # even when a state file is sitting around.
    monkeypatch.setenv("SOMATIC_CACHE_DIR", str(tmp_path))
    (tmp_path / "headless_state.json").write_text(json.dumps({
        "display": ":99", "xauthority": "/tmp/x.auth", "xvfb_pid": 999999999,
    }), encoding="utf-8")
    monkeypatch.delenv("DISPLAY", raising=False)
    headless.apply_active_env()
    assert "DISPLAY" not in os.environ


def test_apply_active_env_no_op_when_no_state(monkeypatch, tmp_path):
    monkeypatch.setenv("SOMATIC_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("SOMATIC_HEADLESS_DISABLE", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    headless.apply_active_env()
    assert "DISPLAY" not in os.environ


def test_apply_active_env_overlays_when_state_is_live(monkeypatch, tmp_path):
    monkeypatch.setenv("SOMATIC_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("SOMATIC_HEADLESS_DISABLE", raising=False)
    # Use the current pytest PID as a guaranteed-alive PID.
    state = {
        "display": ":99",
        "xvfb_pid": os.getpid(),
        "xauthority": "/tmp/x.auth",
        "dbus_address": "unix:abstract=test",
    }
    (tmp_path / "headless_state.json").write_text(json.dumps(state), encoding="utf-8")

    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("XAUTHORITY", raising=False)
    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS", raising=False)
    headless.apply_active_env()
    assert os.environ["DISPLAY"] == ":99"
    assert os.environ["XAUTHORITY"] == "/tmp/x.auth"
    assert os.environ["DBUS_SESSION_BUS_ADDRESS"] == "unix:abstract=test"


def test_active_state_returns_none_for_dead_pid(monkeypatch, tmp_path):
    monkeypatch.setenv("SOMATIC_CACHE_DIR", str(tmp_path))
    # PID 999999999 is essentially guaranteed to not be alive.
    (tmp_path / "headless_state.json").write_text(json.dumps({
        "display": ":99", "xvfb_pid": 999999999, "xauthority": "/tmp/x.auth",
    }), encoding="utf-8")
    assert headless.active_state() is None
    assert headless.is_active() is False


def test_status_when_no_session():
    assert headless.status() == {"active": False}


def test_electron_heuristic_adds_no_sandbox():
    assert headless._maybe_inject_electron_flags(["discord"]) == ["discord", "--no-sandbox"]
    assert headless._maybe_inject_electron_flags(["/usr/bin/discord", "--start-minimized"]) == [
        "/usr/bin/discord",
        "--no-sandbox",
        "--start-minimized",
    ]
    # Already has the flag — must not duplicate.
    assert headless._maybe_inject_electron_flags(["discord", "--no-sandbox"]) == [
        "discord",
        "--no-sandbox",
    ]
    # Unknown binary — leave untouched.
    assert headless._maybe_inject_electron_flags(["xeyes"]) == ["xeyes"]
    # AppImage detection.
    assert headless._maybe_inject_electron_flags(["My.AppImage"]) == ["My.AppImage", "--no-sandbox"]
    # Empty argv — return as-is.
    assert headless._maybe_inject_electron_flags([]) == []


def test_subprocess_env_returns_fresh_dict_with_no_active_session(monkeypatch, tmp_path):
    monkeypatch.setenv("SOMATIC_CACHE_DIR", str(tmp_path))
    env = headless.subprocess_env()
    assert env is not os.environ
    # No DISPLAY overlay when no session active (and disable flag set by conftest).
    assert env.get("DISPLAY") == os.environ.get("DISPLAY")


def test_resolve_display_num_explicit():
    assert headless._resolve_display_num(":42") == 42


def test_resolve_display_num_rejects_bad_format():
    with pytest.raises(SomaticError) as exc:
        headless._resolve_display_num("99")  # missing colon
    assert exc.value.code == "headless_invalid_display"


def test_launch_app_errors_when_not_active(monkeypatch, tmp_path):
    monkeypatch.setenv("SOMATIC_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(headless, "supported_platform", lambda: True)
    with pytest.raises(SomaticError) as exc:
        headless.launch_app(["xeyes"])
    assert exc.value.code == "headless_not_active"


@linux_only
def test_full_lifecycle_smoke(tmp_path, monkeypatch):
    """End-to-end on a Linux box with Xvfb installed: start → status → stop."""
    import shutil

    if shutil.which("Xvfb") is None or shutil.which("xauth") is None:
        pytest.skip("Xvfb and xauth are required for the lifecycle smoke")

    monkeypatch.setenv("SOMATIC_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("SOMATIC_HEADLESS_DISABLE", raising=False)

    result = headless.start(vnc=False, wm=None, adopt_vision_daemon=False)
    try:
        assert result["started"] is True
        assert headless.is_active()
        status = headless.status()
        assert status["active"] is True
        assert status["display"].startswith(":")
    finally:
        stop_result = headless.stop()
        assert stop_result["stopped"] is True
    assert headless.is_active() is False
