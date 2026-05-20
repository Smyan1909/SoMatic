from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__
from . import automation
from .doctor import run_doctor
from .jsonio import SomaticError, command_response
from .vision_client import DEFAULT_VISION_URL, health


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="somatic", description="Native UI automation CLI for agents.")
    parser.add_argument("--version", action="version", version=f"somatic {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    shot = sub.add_parser("screenshot", help="Capture a screenshot, optionally annotated with Set-of-Marks IDs.")
    shot.add_argument("--annotate", action="store_true")
    shot.add_argument("--output-dir", type=Path)
    shot.add_argument("--input", type=Path, help="Use an existing screenshot file instead of capturing the screen.")
    shot.add_argument("--session", default="default")
    shot.add_argument("--marks-out", type=Path)
    shot.add_argument("--vision-url", default=None)
    shot.add_argument("--image", action="store_true", help="Include base64 PNG bytes in the JSON response (for programmatic pipelines).")

    click = sub.add_parser("click", help="Click a mark id or x,y coordinate.")
    click.add_argument("target")
    click.add_argument("--button", default="left")
    click.add_argument("--clicks", type=int, default=1)
    click.add_argument("--interval", type=float, default=0.0)
    add_target_options(click)

    click_near = sub.add_parser("click-near", help="Click at a mark id (or x,y) plus a dx/dy offset.")
    click_near.add_argument("target")
    click_near.add_argument("--dx", type=int, default=0, help="Pixel offset from the anchor's center along the X axis.")
    click_near.add_argument("--dy", type=int, default=0, help="Pixel offset from the anchor's center along the Y axis.")
    click_near.add_argument("--button", default="left")
    click_near.add_argument("--clicks", type=int, default=1)
    click_near.add_argument("--interval", type=float, default=0.0)
    add_target_options(click_near)

    for name, button in [("double-click", "left"), ("right-click", "right"), ("middle-click", "middle")]:
        cmd = sub.add_parser(name, help=f"{name.replace('-', ' ').title()} a mark id or x,y coordinate.")
        cmd.add_argument("target")
        cmd.set_defaults(button_default=button)
        add_target_options(cmd)

    for name in ["mouse-down", "mouse-up"]:
        cmd = sub.add_parser(name, help=f"{name.replace('-', ' ').title()} at the current pointer or target.")
        cmd.add_argument("target", nargs="?")
        cmd.add_argument("--button", default="left")
        add_target_options(cmd)

    move = sub.add_parser("move", help="Move pointer to a mark id or x,y coordinate.")
    move.add_argument("target")
    move.add_argument("--duration", type=float, default=0.0)
    add_target_options(move)

    drag = sub.add_parser("drag", help="Drag pointer to a mark id or x,y coordinate.")
    drag.add_argument("target")
    drag.add_argument("--duration", type=float, default=0.25)
    drag.add_argument("--button", default="left")
    add_target_options(drag)

    scroll = sub.add_parser("scroll", help="Scroll, optionally at a target mark or coordinate.")
    scroll.add_argument("amount", type=int)
    scroll.add_argument("--target")
    add_target_options(scroll)

    type_cmd = sub.add_parser("type", help="Type text.")
    type_cmd.add_argument("text")
    type_cmd.add_argument("--interval", type=float, default=0.0)
    type_cmd.add_argument("--dry-run", action="store_true")

    write_cmd = sub.add_parser("write", help="Alias for `type`.")
    write_cmd.add_argument("text")
    write_cmd.add_argument("--interval", type=float, default=0.0)
    write_cmd.add_argument("--dry-run", action="store_true")

    hotkey = sub.add_parser("hotkey", help="Press a key chord.")
    hotkey.add_argument("keys", nargs="+")
    hotkey.add_argument("--dry-run", action="store_true")

    press = sub.add_parser("press", help="Press a single key.")
    press.add_argument("key")
    press.add_argument("--presses", type=int, default=1)
    press.add_argument("--interval", type=float, default=0.0)
    press.add_argument("--dry-run", action="store_true")

    key_down = sub.add_parser("key-down", help="Hold a key down.")
    key_down.add_argument("key")
    key_down.add_argument("--dry-run", action="store_true")

    key_up = sub.add_parser("key-up", help="Release a key.")
    key_up.add_argument("key")
    key_up.add_argument("--dry-run", action="store_true")

    wait = sub.add_parser("wait", help="Wait for a number of seconds.")
    wait.add_argument("seconds", type=float, nargs="?", default=1.0)

    sub.add_parser("position", help="Report pointer position.")
    sub.add_parser("size", help="Report screen size.")
    sub.add_parser("doctor", help="Check platform and dependency readiness.")
    sub.add_parser("bootstrap", help="Run first-install readiness checks.")

    pause = sub.add_parser("pause", help="Set PyAutoGUI global pause for this process.")
    pause.add_argument("seconds", type=float)

    failsafe = sub.add_parser("failsafe", help="Read or set PyAutoGUI fail-safe status.")
    state = failsafe.add_mutually_exclusive_group()
    state.add_argument("--enable", action="store_true")
    state.add_argument("--disable", action="store_true")

    locate = sub.add_parser("locate", help="Locate an image on screen using PyAutoGUI.")
    locate.add_argument("image", type=Path)
    locate.add_argument("--confidence", type=float)
    locate.add_argument("--all", action="store_true", dest="all_matches")

    center = sub.add_parser("center", help="Locate an image and return its center.")
    center.add_argument("image", type=Path)
    center.add_argument("--confidence", type=float)

    windows = sub.add_parser("windows", help="Report active or visible windows where supported.")
    win_sub = windows.add_subparsers(dest="window_command", required=True)
    win_sub.add_parser("active")
    list_cmd = win_sub.add_parser("list")
    list_cmd.add_argument("--title")

    vision = sub.add_parser("vision", help="Manage the local YOLO ONNX vision daemon.")
    vision_sub = vision.add_subparsers(dest="vision_command", required=True)
    init_cmd = vision_sub.add_parser("init", help="Load the YOLO ONNX model and start the daemon.")
    init_cmd.add_argument("--timeout", type=float, default=600.0, help="Seconds to wait for the daemon to report ready.")
    vision_sub.add_parser("stop", help="Stop the vision daemon and free model memory.")
    status = vision_sub.add_parser("status", help="Report daemon health.")
    status.add_argument("--url", default=DEFAULT_VISION_URL)

    mcp = sub.add_parser("mcp", help="Run SoMatic as an MCP server over stdio.")
    mcp_sub = mcp.add_subparsers(dest="mcp_command", required=True)
    mcp_sub.add_parser("serve", help="Serve on stdio (intended for Claude Code, Cursor, and other MCP clients).")

    sub.add_parser("skill", help="Print the SoMatic operating-loop guidance (mirror of the `skill` MCP prompt).")

    sub.add_parser("license", help="Print SoMatic's MIT license summary and the AGPL notice for vision weights.")

    headless = sub.add_parser("headless", help="Manage a headless Xvfb session (Linux only).")
    headless_sub = headless.add_subparsers(dest="headless_command", required=True)

    h_start = headless_sub.add_parser("start", help="Start a virtual X display and optional window manager / VNC / apps.")
    h_start.add_argument("--display", default=None, help="Explicit display number, e.g. ':99'. Auto-picked if omitted.")
    h_start.add_argument("--geometry", default="1920x1080x24", help="WIDTHxHEIGHTxDEPTH for the virtual screen.")
    h_start.add_argument("--wm", default="openbox", help="Window manager binary to spawn. Pass --no-wm to skip.")
    h_start.add_argument("--no-wm", dest="no_wm", action="store_true", help="Skip spawning a window manager.")
    h_start.add_argument("--launch", action="append", default=[], help="Command to launch inside the session (repeatable; each is shell-split).")
    h_start.add_argument("--vnc", action="store_true", help="Also spawn x11vnc bound to localhost for live viewing.")
    h_start.add_argument("--vnc-port", type=int, default=5900, help="Port for x11vnc when --vnc is set.")
    h_start.add_argument("--no-adopt-vision-daemon", dest="no_adopt", action="store_true", help="Leave the vision daemon alone instead of restarting it under the new DISPLAY.")

    headless_sub.add_parser("stop", help="Stop the active headless session and clean up resources.")
    headless_sub.add_parser("status", help="Report whether a headless session is active and its details.")

    h_launch = headless_sub.add_parser("launch", help="Launch a program inside the active headless session.")
    h_launch.add_argument("argv", nargs=argparse.REMAINDER, help="Command and arguments to launch.")

    return parser


def add_target_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--session", default="default")
    parser.add_argument("--marks", type=Path)
    parser.add_argument("--dry-run", action="store_true")


def dispatch(args: argparse.Namespace) -> tuple[str, object]:
    command = args.command
    if command == "screenshot":
        return command, lambda: screenshot_command(args)
    if command == "click":
        return command, lambda: automation.click(args.target, button=args.button, clicks=args.clicks, interval=args.interval, session=args.session, marks_path=args.marks, dry_run=args.dry_run)
    if command == "click-near":
        return command, lambda: automation.click_near(args.target, dx=args.dx, dy=args.dy, button=args.button, clicks=args.clicks, interval=args.interval, session=args.session, marks_path=args.marks, dry_run=args.dry_run)
    if command == "double-click":
        return command, lambda: automation.click(args.target, button=args.button_default, clicks=2, session=args.session, marks_path=args.marks, dry_run=args.dry_run)
    if command in {"right-click", "middle-click"}:
        return command, lambda: automation.click(args.target, button=args.button_default, clicks=1, session=args.session, marks_path=args.marks, dry_run=args.dry_run)
    if command == "mouse-down":
        return command, lambda: automation.mouse_down(args.target, button=args.button, session=args.session, marks_path=args.marks, dry_run=args.dry_run)
    if command == "mouse-up":
        return command, lambda: automation.mouse_up(args.target, button=args.button, session=args.session, marks_path=args.marks, dry_run=args.dry_run)
    if command == "move":
        return command, lambda: automation.move(args.target, duration=args.duration, session=args.session, marks_path=args.marks, dry_run=args.dry_run)
    if command == "drag":
        return command, lambda: automation.drag(args.target, duration=args.duration, button=args.button, session=args.session, marks_path=args.marks, dry_run=args.dry_run)
    if command == "scroll":
        return command, lambda: automation.scroll(args.amount, target=args.target, session=args.session, marks_path=args.marks, dry_run=args.dry_run)
    if command in {"type", "write"}:
        return command, lambda: automation.type_text(args.text, interval=args.interval, dry_run=args.dry_run)
    if command == "hotkey":
        return command, lambda: automation.hotkey(args.keys, dry_run=args.dry_run)
    if command == "press":
        return command, lambda: automation.press(args.key, presses=args.presses, interval=args.interval, dry_run=args.dry_run)
    if command == "key-down":
        return command, lambda: automation.key_down(args.key, dry_run=args.dry_run)
    if command == "key-up":
        return command, lambda: automation.key_up(args.key, dry_run=args.dry_run)
    if command == "wait":
        return command, lambda: automation.wait(args.seconds)
    if command == "position":
        return command, automation.position
    if command == "size":
        return command, automation.screen_size
    if command == "doctor":
        return command, run_doctor
    if command == "bootstrap":
        return command, bootstrap
    if command == "pause":
        return command, lambda: automation.set_pause(args.seconds)
    if command == "failsafe":
        enabled = True if args.enable else False if args.disable else None
        return command, lambda: automation.fail_safe_status(enabled)
    if command == "locate":
        return command, lambda: automation.locate_on_screen(args.image, confidence=args.confidence, all_matches=args.all_matches)
    if command == "center":
        return command, lambda: center_image(args.image, args.confidence)
    if command == "windows":
        if args.window_command == "active":
            return "windows active", automation.active_window
        if args.window_command == "list":
            return "windows list", lambda: automation.list_windows(args.title)
    if command == "vision":
        if args.vision_command == "init":
            return "vision init", lambda: vision_init_command(timeout=args.timeout)
        if args.vision_command == "stop":
            return "vision stop", lambda: vision_stop_command()
        if args.vision_command == "status":
            return "vision status", lambda: vision_status_command(args.url)
    if command == "skill":
        return "skill", skill_command
    if command == "license":
        return "license", license_command
    if command == "mcp" and args.mcp_command == "serve":
        return "mcp serve", _mcp_serve_marker
    if command == "headless":
        if args.headless_command == "start":
            return "headless start", lambda: headless_start_command(args)
        if args.headless_command == "stop":
            return "headless stop", headless_stop_command
        if args.headless_command == "status":
            return "headless status", headless_status_command
        if args.headless_command == "launch":
            return "headless launch", lambda: headless_launch_command(args)
    raise AssertionError(f"unhandled command {command}")


# Sentinel returned by dispatch() for `mcp serve`. main() checks for it and
# starts the MCP server directly instead of wrapping the (blocking) run in
# command_response (which would also pollute stdout — stdout is the MCP
# transport channel).
_mcp_serve_marker = object()


def screenshot_command(args: argparse.Namespace) -> dict[str, object]:
    from .screenshot import screenshot

    return screenshot(
        annotate=args.annotate,
        output_dir=args.output_dir,
        input_path=args.input,
        session=args.session,
        marks_out=args.marks_out,
        vision_url=args.vision_url,
        include_image_bytes=args.image,
    )


def skill_command() -> dict[str, object]:
    from .skill import skill_text

    return {"text": skill_text()}


def license_command() -> dict[str, object]:
    from . import licenses

    return {
        "somatic": licenses.somatic_license(),
        "vision_weights": licenses.vision_weights_notice(),
    }


def headless_start_command(args: argparse.Namespace) -> dict[str, object]:
    import shlex

    from . import headless

    launch_list = [shlex.split(item) for item in (args.launch or []) if item]
    wm = None if args.no_wm else args.wm
    return headless.start(
        display=args.display,
        geometry=args.geometry,
        wm=wm,
        launch=launch_list or None,
        vnc=args.vnc,
        vnc_port=args.vnc_port,
        adopt_vision_daemon=not args.no_adopt,
    )


def headless_stop_command() -> dict[str, object]:
    from . import headless

    return headless.stop()


def headless_status_command() -> dict[str, object]:
    from . import headless

    return headless.status()


def headless_launch_command(args: argparse.Namespace) -> dict[str, object]:
    from . import headless
    from .jsonio import fail as _fail

    argv = [token for token in (args.argv or []) if token]
    if not argv:
        _fail("headless_launch_empty", "Provide a command to launch.")
    return headless.launch_app(argv)


def vision_init_command(*, timeout: float) -> dict[str, object]:
    from .vision_daemon import start_daemon

    return start_daemon(timeout=timeout)


def vision_stop_command() -> dict[str, object]:
    from .vision_daemon import stop_daemon

    return stop_daemon()


def vision_status_command(url: str) -> dict[str, object]:
    try:
        status = health(server_url=url)
        return {"running": True, **status}
    except SomaticError as exc:
        if exc.code != "vision_unavailable":
            raise
        return {"running": False, "url": url, "error": {"code": exc.code, "message": exc.message, "details": exc.details}}


def center_image(image: Path, confidence: float | None) -> dict[str, object]:
    result = automation.locate_on_screen(image, confidence=confidence)
    return {"found": result["found"], "image": str(image), "center": result.get("center")}


def bootstrap() -> dict[str, object]:
    report = run_doctor()
    return {
        "ready": report["ready"],
        "doctor": report,
        "next_steps": [
            "Run `somatic vision init` to download the YOLO ONNX model (first run only) and start the vision daemon.",
            "Then run `somatic screenshot --annotate`; release model memory with `somatic vision stop` when finished.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    # If a headless session is active, transparently inherit DISPLAY etc. so
    # every subsequent command (click, screenshot, …) operates on the virtual
    # desktop. The headless module no-ops when SOMATIC_HEADLESS_DISABLE=1
    # (set by tests) or when no session is active.
    from . import headless as _headless

    _headless.apply_active_env()

    parser = build_parser()
    args = parser.parse_args(argv)
    command, func = dispatch(args)
    if func is _mcp_serve_marker:
        from .mcp_server import serve as _mcp_serve

        # MCP uses stdio as its transport, so we must NOT emit any JSON envelope
        # to stdout. command_response() is skipped on this path.
        _mcp_serve()
        return 0
    return command_response(command, func)  # type: ignore[arg-type]


if __name__ == "__main__":
    raise SystemExit(main())
