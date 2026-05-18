from __future__ import annotations

import json
from typing import Any

from . import automation, headless as _headless, licenses as _licenses
from .screenshot import screenshot as _screenshot
from .skill import skill_summary, skill_text
from .vision_client import health as _health
from .vision_daemon import start_daemon, stop_daemon

try:
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ImageContent, TextContent
except Exception as exc:  # pragma: no cover - surfaced at runtime if extra missing
    raise SystemExit(
        "The `mcp` package is required to run the SoMatic MCP server. "
        "Install with `pip install -e .[mcp]`."
    ) from exc


mcp = FastMCP("somatic", instructions=skill_summary())


@mcp.prompt(name="skill", description="Load the SoMatic operating loop (Set-of-Marks workflow).")
def skill_prompt() -> str:
    return skill_text()


@mcp.prompt(name="license", description="SoMatic license summary plus AGPL notice for the vision weights.")
def license_prompt() -> str:
    return _licenses.combined()


# ---------- vision lifecycle ----------

@mcp.tool()
def vision_init(timeout: float = 600.0) -> dict[str, Any]:
    """Load the YOLO ONNX model into a background daemon. First-ever call may
    take 1–3 minutes (.pt → .onnx conversion on first run); later calls are
    near-instant. Call this once at the start of a session before taking
    annotated screenshots."""
    return start_daemon(timeout=timeout)


@mcp.tool()
def vision_stop() -> dict[str, Any]:
    """Stop the vision daemon and free model memory. Call at the end of a session."""
    return stop_daemon()


@mcp.tool()
def vision_status() -> dict[str, Any]:
    """Report whether the vision daemon is loaded and responsive."""
    return _health()


# ---------- screenshots ----------

def _screenshot_content(*, annotate: bool, session: str) -> list[ImageContent | TextContent]:
    result = _screenshot(annotate=annotate, session=session, include_image_bytes=True)
    # Pop the bytes out of the JSON envelope before serialising the text block
    # so the same bytes don't appear twice in the MCP response.
    raw_b64 = result.pop("image_b64", None)
    raw_mime = result.pop("image_mime", "image/png")
    annotated_b64 = result.pop("annotated_image_b64", None)
    annotated_mime = result.pop("annotated_image_mime", "image/png")

    content: list[ImageContent | TextContent] = []
    # When annotated, prefer the annotated image as the primary visual content
    # so agents reason about the marked-up version first.
    if annotated_b64:
        content.append(ImageContent(type="image", data=annotated_b64, mimeType=annotated_mime))
    elif raw_b64:
        content.append(ImageContent(type="image", data=raw_b64, mimeType=raw_mime))
    content.append(TextContent(type="text", text=json.dumps(result, indent=2, sort_keys=True)))
    return content


@mcp.tool()
def screenshot_annotated(session: str = "default") -> list[ImageContent | TextContent]:
    """Capture the screen, run YOLO ONNX, and return the **annotated** image
    inline (with numbered marks drawn over each detected element) plus the
    marks JSON as text. Call this before every consequential action so you
    can act on fresh mark IDs.

    Requires `vision_init` to have been called first.
    """
    return _screenshot_content(annotate=True, session=session)


@mcp.tool()
def screenshot(session: str = "default") -> list[ImageContent | TextContent]:
    """Capture a raw screenshot without running the vision model. Returns the
    PNG inline plus dimension metadata. Use `screenshot_annotated` instead if
    you intend to act on UI elements — that's the path with mark IDs."""
    return _screenshot_content(annotate=False, session=session)


# ---------- pointer ----------

@mcp.tool()
def click(target: str, button: str = "left", clicks: int = 1, session: str = "default") -> dict[str, Any]:
    """Click a UI element. `target` is either a mark id (e.g. "5") or an
    explicit coordinate as "x,y" (e.g. "640,420"). Prefer mark IDs from a
    fresh `screenshot_annotated` response."""
    return automation.click(target, button=button, clicks=clicks, session=session)


@mcp.tool()
def click_near(target: str, dx: int = 0, dy: int = 0, button: str = "left", clicks: int = 1, session: str = "default") -> dict[str, Any]:
    """Click at an anchor (mark id or x,y) plus a pixel offset. Use this when
    YOLO didn't annotate the exact target but did annotate a nearby element —
    e.g. clicking a text input that sits to the right of an attach (+) button:
    `click_near("12", dx=300, dy=0)`."""
    return automation.click_near(target, dx=dx, dy=dy, button=button, clicks=clicks, session=session)


@mcp.tool()
def move(target: str, duration: float = 0.0, session: str = "default") -> dict[str, Any]:
    """Move the pointer to a mark id or x,y coordinate."""
    return automation.move(target, duration=duration, session=session)


@mcp.tool()
def scroll(amount: int, target: str | None = None, session: str = "default") -> dict[str, Any]:
    """Scroll vertically. Positive scrolls up, negative scrolls down. Optionally
    pass a `target` mark id or x,y to move the pointer first."""
    return automation.scroll(amount, target=target, session=session)


# ---------- keyboard ----------

@mcp.tool()
def type_text(text: str, interval: float = 0.0) -> dict[str, Any]:
    """Type a string of text into the currently focused field."""
    return automation.type_text(text, interval=interval)


@mcp.tool()
def hotkey(keys: list[str]) -> dict[str, Any]:
    """Press a key chord. Example: hotkey(["ctrl", "s"])."""
    return automation.hotkey(keys)


@mcp.tool()
def press(key: str, presses: int = 1) -> dict[str, Any]:
    """Press a single key, optionally repeated."""
    return automation.press(key, presses=presses)


@mcp.tool()
def wait(seconds: float = 1.0) -> dict[str, Any]:
    """Sleep for the given number of seconds. Useful between an action and a
    follow-up screenshot to let the UI catch up."""
    return automation.wait(seconds)


# ---------- headless (Linux-only) ----------

@mcp.tool()
def headless_start(
    geometry: str = "1920x1080x24",
    wm: str = "openbox",
    vnc: bool = False,
    vnc_port: int = 5900,
    launch: list[list[str]] | None = None,
    adopt_vision_daemon: bool = True,
) -> dict[str, Any]:
    """Spawn an Xvfb virtual desktop (Linux only). Subsequent SoMatic actions
    automatically operate on the virtual display. Pass `launch` to bring up apps
    inside the session in one call (e.g. `[["discord"], ["firefox"]]`). Set
    `vnc=true` to also bring up x11vnc on localhost for live debugging.

    Returns `{"started": true, "display": ":99", ...}` on success or an error
    envelope with `code: "headless_unsupported_platform"` on macOS/Windows."""
    return _headless.start(
        geometry=geometry,
        wm=wm or None,
        vnc=vnc,
        vnc_port=vnc_port,
        launch=launch,
        adopt_vision_daemon=adopt_vision_daemon,
    )


@mcp.tool()
def headless_stop() -> dict[str, Any]:
    """Stop the active headless session and clean up Xvfb / WM / D-Bus / VNC /
    spawned apps. Removes the state file so subsequent SoMatic commands return
    to the real display."""
    return _headless.stop()


@mcp.tool()
def headless_status() -> dict[str, Any]:
    """Report whether a headless session is active and its details (display,
    geometry, VNC URL if enabled, launched app PIDs)."""
    return _headless.status()


@mcp.tool()
def headless_launch(command: list[str]) -> dict[str, Any]:
    """Launch a program inside the active headless session. Electron apps
    (Discord, Slack, Obsidian, .AppImage, etc.) automatically get
    `--no-sandbox` added unless already present."""
    return _headless.launch_app(command)


# ---------- entry points ----------

def serve() -> None:
    """Run the MCP server over stdio (the transport Claude Code expects)."""
    mcp.run()


def main() -> int:
    serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
