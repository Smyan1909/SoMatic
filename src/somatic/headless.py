"""Headless desktop mode for SoMatic.

Spawns an Xvfb virtual X server (plus optional window manager, D-Bus session,
VNC server, and pre-launched apps) so SoMatic actions run against a virtual
display instead of the user's real screen. Linux-only — Xvfb has no equivalent
on macOS/Windows, so non-Linux invocations fail fast with a clear error.

State persists in `cache_dir() / "headless_state.json"` so that subsequent
SoMatic CLI processes (`somatic click`, `somatic screenshot`, ...) inherit
DISPLAY / XAUTHORITY / DBUS_SESSION_BUS_ADDRESS automatically via
`apply_active_env()`.
"""
from __future__ import annotations

import json
import os
import platform
import secrets
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

from .jsonio import fail
from .paths import (
    cache_dir,
    headless_log_file,
    headless_state_file,
    headless_xauth_file,
)

DEFAULT_GEOMETRY = "1920x1080x24"
DEFAULT_DISPLAY_RANGE = range(99, 200)
READY_TIMEOUT_SECONDS = 5.0

# Electron-based apps that need --no-sandbox under Xvfb. Conservative list;
# anything outside it goes through untouched.
_ELECTRON_BIN_NAMES = {
    "discord",
    "discord-canary",
    "discord-ptb",
    "slack",
    "obsidian",
    "code",
    "code-insiders",
    "signal-desktop",
    "element-desktop",
    "logseq",
    "notion-snap",
}


# ---------------------------------------------------------------------------
# platform + state
# ---------------------------------------------------------------------------


def supported_platform() -> bool:
    return platform.system() == "Linux"


def _platform_guard() -> None:
    if not supported_platform():
        fail(
            "headless_unsupported_platform",
            "Headless mode requires Xvfb and is only supported on Linux. See docs/headless.md.",
            details={"platform": platform.system()},
        )


def active_state() -> dict[str, Any] | None:
    """Return the parsed state file if a session is genuinely active, else None.

    A session is "genuinely active" only when the state file exists, parses,
    and its Xvfb PID is alive. Stale files (e.g. after a crash) return None.
    """
    path = headless_state_file()
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    pid = state.get("xvfb_pid")
    if not _pid_alive(pid):
        return None
    return state


def is_active() -> bool:
    return active_state() is not None


def status() -> dict[str, Any]:
    state = active_state()
    if state is None:
        return {"active": False}
    response: dict[str, Any] = {
        "active": True,
        "display": state.get("display"),
        "geometry": state.get("geometry"),
        "wm": state.get("wm"),
        "vnc_enabled": state.get("vnc_enabled", False),
        "apps": state.get("apps", []),
        "started_at": state.get("started_at"),
        "xauthority": state.get("xauthority"),
    }
    if state.get("vnc_enabled"):
        port = state.get("vnc_port")
        if port:
            response["vnc_url"] = f"vnc://127.0.0.1:{port}"
            response["vnc_port"] = port
    return response


# ---------------------------------------------------------------------------
# env application across CLI invocations
# ---------------------------------------------------------------------------


def apply_active_env() -> None:
    """If a headless session is active, set DISPLAY/XAUTHORITY/D-Bus in os.environ.

    Honours SOMATIC_HEADLESS_DISABLE=1 so pytest (and any CI environment that
    sets it) never accidentally inherits a developer's local headless session.
    """
    if os.environ.get("SOMATIC_HEADLESS_DISABLE") == "1":
        return
    state = active_state()
    if state is None:
        return
    display = state.get("display")
    if display:
        os.environ["DISPLAY"] = display
    xauth = state.get("xauthority")
    if xauth:
        os.environ["XAUTHORITY"] = xauth
    dbus = state.get("dbus_address")
    if dbus:
        os.environ["DBUS_SESSION_BUS_ADDRESS"] = dbus


def subprocess_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Full env dict suitable for subprocess.Popen, with active headless overlays.

    Always returns a fresh dict (never the live os.environ) so callers can
    pass it as `env=` without surprising shared-mutation semantics.
    """
    env = dict(os.environ)
    state = active_state()
    if state is not None and os.environ.get("SOMATIC_HEADLESS_DISABLE") != "1":
        display = state.get("display")
        if display:
            env["DISPLAY"] = display
        xauth = state.get("xauthority")
        if xauth:
            env["XAUTHORITY"] = xauth
        dbus = state.get("dbus_address")
        if dbus:
            env["DBUS_SESSION_BUS_ADDRESS"] = dbus
    if extra:
        env.update(extra)
    return env


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------


def start(
    *,
    display: str | None = None,
    geometry: str = DEFAULT_GEOMETRY,
    wm: str | None = "openbox",
    launch: list[list[str]] | None = None,
    vnc: bool = False,
    vnc_port: int = 5900,
    adopt_vision_daemon: bool = True,
) -> dict[str, Any]:
    _platform_guard()

    existing = active_state()
    if existing is not None:
        return {"already_active": True, **status()}

    display_num = _resolve_display_num(display)
    chosen_display = f":{display_num}"

    # Sweep stale locks before we spawn (only if the holder is dead).
    _sweep_stale_locks(display_num)

    # Vision daemon adoption — note original state so we can report it.
    previous_daemon_display: str | None = None
    if adopt_vision_daemon:
        from . import vision_daemon

        if _is_vision_daemon_running():
            previous_daemon_display = os.environ.get("DISPLAY")
            vision_daemon.stop_daemon()

    xauth_path = headless_xauth_file()
    _bootstrap_xauthority(display_num, xauth_path)

    log_path = headless_log_file()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    xvfb_proc = _spawn_xvfb(display_num, geometry, xauth_path, log_path)

    if not _wait_for_x_socket(display_num, READY_TIMEOUT_SECONDS):
        _terminate(xvfb_proc.pid)
        fail(
            "xvfb_not_ready",
            f"Xvfb on {chosen_display} did not become ready within {READY_TIMEOUT_SECONDS:.0f}s.",
            details={"log_path": str(log_path), "display": chosen_display},
        )

    # Now that X is up, expose env so dbus-launch / WM / apps inherit it.
    overlay_env = {
        "DISPLAY": chosen_display,
        "XAUTHORITY": str(xauth_path),
    }

    dbus_address, dbus_pid = _launch_dbus(overlay_env)
    if dbus_address:
        overlay_env["DBUS_SESSION_BUS_ADDRESS"] = dbus_address

    wm_pid: int | None = None
    if wm:
        wm_proc = _spawn_background(
            shutil.which(wm) or wm,
            extra_env=overlay_env,
            log_path=log_path,
        )
        wm_pid = wm_proc.pid if wm_proc is not None else None

    vnc_pid: int | None = None
    if vnc:
        vnc_proc = _spawn_x11vnc(display_num, xauth_path, vnc_port, overlay_env, log_path)
        vnc_pid = vnc_proc.pid if vnc_proc is not None else None

    state: dict[str, Any] = {
        "version": 1,
        "display": chosen_display,
        "display_num": display_num,
        "geometry": geometry,
        "xvfb_pid": xvfb_proc.pid,
        "wm": wm if wm_pid else None,
        "wm_pid": wm_pid,
        "dbus_address": dbus_address,
        "dbus_pid": dbus_pid,
        "vnc_enabled": bool(vnc_pid),
        "vnc_port": vnc_port if vnc_pid else None,
        "vnc_pid": vnc_pid,
        "xauthority": str(xauth_path),
        "apps": [],
        "started_at": time.time(),
    }
    _write_state(state)

    # Adopt vision daemon: re-launch under new DISPLAY now that state file is
    # present (so daemon's own apply_active_env picks it up via the env overlay
    # we pass to subprocess).
    vision_daemon_info: dict[str, Any] = {"adopted": False}
    if adopt_vision_daemon and previous_daemon_display is not None:
        from . import vision_daemon

        result = vision_daemon.start_daemon()
        vision_daemon_info = {
            "adopted": True,
            "previous_display": previous_daemon_display,
            "result": result,
        }

    # Launch any pre-requested apps now.
    apps_launched: list[dict[str, Any]] = []
    if launch:
        for argv in launch:
            apps_launched.append(launch_app(argv))

    return {
        "started": True,
        "display": chosen_display,
        "geometry": geometry,
        "wm": state["wm"],
        "vnc_enabled": state["vnc_enabled"],
        **({"vnc_url": f"vnc://127.0.0.1:{vnc_port}"} if vnc_pid else {}),
        "apps_launched": apps_launched,
        "vision_daemon": vision_daemon_info,
        "log_path": str(log_path),
    }


# ---------------------------------------------------------------------------
# stop
# ---------------------------------------------------------------------------


def stop() -> dict[str, Any]:
    _platform_guard()
    path = headless_state_file()
    if not path.exists():
        return {"stopped": False, "reason": "not_active"}

    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        path.unlink(missing_ok=True)
        return {"stopped": False, "reason": "state_unreadable"}

    display = state.get("display", ":99")
    display_num = state.get("display_num")

    previous_daemon_display = display
    daemon_was_running = _is_vision_daemon_running()
    if daemon_was_running:
        from . import vision_daemon

        vision_daemon.stop_daemon()

    # Kill order: VNC → apps → WM → D-Bus → Xvfb.
    for pid in [state.get("vnc_pid"), *(app.get("pid") for app in state.get("apps", []))]:
        _terminate(pid)
    _terminate(state.get("wm_pid"))
    _terminate(state.get("dbus_pid"))
    _terminate(state.get("xvfb_pid"))

    # Best-effort orphan sweep for double-forked Electron helpers etc.
    if display:
        try:
            subprocess.run(
                ["pkill", "-f", f"DISPLAY={display}"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            pass

    if isinstance(display_num, int):
        _sweep_stale_locks(display_num, force=True)

    # Remove the per-session Xauthority cookie.
    try:
        Path(state.get("xauthority", "")).unlink(missing_ok=True)
    except OSError:
        pass

    path.unlink(missing_ok=True)

    return {
        "stopped": True,
        "display": display,
        "vision_daemon": {
            "stopped": daemon_was_running,
            "previous_display": previous_daemon_display,
        },
        "apps_killed": len(state.get("apps", [])),
    }


# ---------------------------------------------------------------------------
# launch app into the active session
# ---------------------------------------------------------------------------


def launch_app(argv: list[str]) -> dict[str, Any]:
    _platform_guard()
    state = active_state()
    if state is None:
        fail("headless_not_active", "Run `somatic headless start` before `headless launch`.")
        raise AssertionError("unreachable")
    if not argv:
        fail("headless_launch_empty", "Provide a command to launch.")
        raise AssertionError("unreachable")

    argv = _maybe_inject_electron_flags(list(argv))
    env = subprocess_env()
    log_path = headless_log_file()
    with open(log_path, "ab") as logf:
        proc = subprocess.Popen(  # noqa: S603 - argv is user-supplied by design
            argv,
            env=env,
            stdout=logf,
            stderr=logf,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )

    state.setdefault("apps", []).append({"pid": proc.pid, "argv": argv})
    _write_state(state)

    return {"launched": True, "pid": proc.pid, "argv": argv}


# Public alias matching the MCP/CLI verb shape.
launch = launch_app


# ---------------------------------------------------------------------------
# Electron heuristic
# ---------------------------------------------------------------------------


def _maybe_inject_electron_flags(argv: list[str]) -> list[str]:
    if not argv:
        return argv
    head = Path(argv[0]).name.lower()
    if head.endswith(".appimage") or head in _ELECTRON_BIN_NAMES:
        if "--no-sandbox" not in argv:
            argv = [argv[0], "--no-sandbox", *argv[1:]]
    return argv


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _pid_alive(pid: Any) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        # On Windows, `os.kill(pid, sig)` with sig != CTRL_C_EVENT/CTRL_BREAK_EVENT
        # calls TerminateProcess(handle, sig). That includes sig=0 — which would
        # kill the target with exit code 0 instead of probing existence. Use
        # OpenProcess via ctypes to check liveness without side effects.
        import ctypes
        from ctypes import wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259  # STATUS_PENDING

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we can't signal it — treat as alive.
        return True
    except OSError:
        return False
    return True


def _terminate(pid: Any, *, sigterm_grace: float = 2.0) -> None:
    if not _pid_alive(pid):
        return
    assert isinstance(pid, int)  # narrowed by _pid_alive
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.time() + sigterm_grace
    while time.time() < deadline:
        if not _pid_alive(pid):
            return
        time.sleep(0.05)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def _resolve_display_num(display: str | None) -> int:
    if display is not None:
        if display.startswith(":"):
            try:
                return int(display[1:])
            except ValueError:
                fail("headless_invalid_display", f"Display must look like ':99', got {display!r}.")
        fail("headless_invalid_display", f"Display must look like ':99', got {display!r}.")
    for candidate in DEFAULT_DISPLAY_RANGE:
        lock = Path(f"/tmp/.X{candidate}-lock")
        if not lock.exists():
            return candidate
        # If the lock's PID is dead, we'll reclaim it during the sweep.
        if not _lock_holder_alive(lock):
            return candidate
    fail("headless_no_free_display", "Could not find a free X display number in :99..:199.")
    raise AssertionError("unreachable")


def _lock_holder_alive(lock_path: Path) -> bool:
    try:
        pid = int(lock_path.read_text().strip())
    except (OSError, ValueError):
        return False
    return _pid_alive(pid)


def _sweep_stale_locks(display_num: int, *, force: bool = False) -> None:
    lock = Path(f"/tmp/.X{display_num}-lock")
    sock_dir = Path(f"/tmp/.X11-unix/X{display_num}")
    if lock.exists() and (force or not _lock_holder_alive(lock)):
        lock.unlink(missing_ok=True)
    if sock_dir.exists() and (force or not _lock_holder_alive(lock)):
        try:
            sock_dir.unlink(missing_ok=True)
        except IsADirectoryError:
            shutil.rmtree(sock_dir, ignore_errors=True)


def _wait_for_x_socket(display_num: int, timeout: float) -> bool:
    sock_path = f"/tmp/.X11-unix/X{display_num}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        if Path(sock_path).exists():
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                    s.settimeout(0.05)
                    s.connect(sock_path)
                return True
            except OSError:
                pass
        time.sleep(0.1)
    return False


def _bootstrap_xauthority(display_num: int, xauth_path: Path) -> None:
    xauth_path.parent.mkdir(parents=True, exist_ok=True)
    xauth_path.touch(exist_ok=True)
    cookie = secrets.token_hex(16)
    xauth_bin = shutil.which("xauth")
    if xauth_bin is None:
        fail(
            "xauth_missing",
            "The `xauth` binary is required to bootstrap headless authentication. "
            "Install with `apt install xauth` (or your distro equivalent).",
            details={"display_num": display_num},
        )
    subprocess.run(
        [xauth_bin, "-f", str(xauth_path), "add", f":{display_num}", ".", cookie],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _spawn_xvfb(
    display_num: int, geometry: str, xauth_path: Path, log_path: Path
) -> subprocess.Popen[bytes]:
    xvfb_bin = shutil.which("Xvfb")
    if xvfb_bin is None:
        fail(
            "xvfb_missing",
            "The `Xvfb` binary was not found on PATH. Install with `apt install xvfb`.",
            details={"display_num": display_num},
        )
    argv = [
        xvfb_bin,
        f":{display_num}",
        "-screen",
        "0",
        geometry,
        "-nolisten",
        "tcp",
        "-auth",
        str(xauth_path),
    ]
    log = open(log_path, "ab")
    return subprocess.Popen(  # noqa: S603
        argv,
        stdout=log,
        stderr=log,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )


def _launch_dbus(extra_env: dict[str, str]) -> tuple[str | None, int | None]:
    dbus_bin = shutil.which("dbus-launch")
    if dbus_bin is None:
        return None, None
    env = subprocess_env(extra_env)
    try:
        result = subprocess.run(  # noqa: S603
            [dbus_bin, "--sh-syntax"],
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, None
    address: str | None = None
    pid: int | None = None
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip().rstrip(";")
        if line.startswith("DBUS_SESSION_BUS_ADDRESS="):
            address = line.split("=", 1)[1].strip().strip("'\"")
        elif line.startswith("DBUS_SESSION_BUS_PID="):
            try:
                pid = int(line.split("=", 1)[1].strip().strip("'\""))
            except ValueError:
                pid = None
    return address, pid


def _spawn_background(
    program: str | None,
    *,
    extra_env: dict[str, str],
    log_path: Path,
) -> subprocess.Popen[bytes] | None:
    if not program:
        return None
    binary = shutil.which(program) or program
    if not Path(binary).exists():
        return None
    env = subprocess_env(extra_env)
    log = open(log_path, "ab")
    try:
        return subprocess.Popen(  # noqa: S603
            [binary],
            env=env,
            stdout=log,
            stderr=log,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return None


def _spawn_x11vnc(
    display_num: int,
    xauth_path: Path,
    port: int,
    extra_env: dict[str, str],
    log_path: Path,
) -> subprocess.Popen[bytes] | None:
    binary = shutil.which("x11vnc")
    if binary is None:
        return None
    argv = [
        binary,
        "-display",
        f":{display_num}",
        "-auth",
        str(xauth_path),
        "-rfbport",
        str(port),
        "-localhost",
        "-forever",
        "-shared",
        "-quiet",
        "-nopw",  # localhost-only, password not needed
    ]
    env = subprocess_env(extra_env)
    log = open(log_path, "ab")
    try:
        return subprocess.Popen(  # noqa: S603
            argv,
            env=env,
            stdout=log,
            stderr=log,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return None


def _is_vision_daemon_running() -> bool:
    from .paths import daemon_pid_file

    pid_path = daemon_pid_file()
    if not pid_path.exists():
        return False
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    return _pid_alive(pid)


def _write_state(state: dict[str, Any]) -> None:
    path = headless_state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
