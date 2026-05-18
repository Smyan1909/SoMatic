from __future__ import annotations

import importlib
import time
from pathlib import Path
from typing import Any

from .jsonio import fail
from .marks import get_mark


def pyautogui() -> Any:
    try:
        return importlib.import_module("pyautogui")
    except Exception as exc:
        fail(
            "pyautogui_unavailable",
            "PyAutoGUI could not be imported. Run `somatic doctor` for setup guidance.",
            details={"error": str(exc)},
        )


def parse_target(target: str, *, session: str = "default", marks_path: Path | None = None) -> tuple[int, int, dict[str, Any]]:
    value = target.strip()
    if "," in value:
        left, right = value.split(",", 1)
        return int(float(left)), int(float(right)), {"source": "coordinate"}
    if value.isdigit():
        mark = get_mark(int(value), session=session, path=marks_path)
        return mark.center[0], mark.center[1], {"source": "mark", "mark": mark.to_payload()}
    fail("invalid_target", "Target must be a mark id or `x,y` coordinates.", details={"target": target})
    raise AssertionError("unreachable")


def screen_size() -> dict[str, int]:
    width, height = pyautogui().size()
    return {"width": int(width), "height": int(height)}


def position() -> dict[str, int]:
    x, y = pyautogui().position()
    return {"x": int(x), "y": int(y)}


def click(target: str, *, button: str = "left", clicks: int = 1, interval: float = 0.0, session: str = "default", marks_path: Path | None = None, dry_run: bool = False) -> dict[str, Any]:
    x, y, resolved = parse_target(target, session=session, marks_path=marks_path)
    if not dry_run:
        pyautogui().click(x=x, y=y, clicks=clicks, interval=interval, button=button)
    return {"action": "click", "x": x, "y": y, "button": button, "clicks": clicks, "dry_run": dry_run, "target": resolved}


def click_near(target: str, *, dx: int = 0, dy: int = 0, button: str = "left", clicks: int = 1, interval: float = 0.0, session: str = "default", marks_path: Path | None = None, dry_run: bool = False) -> dict[str, Any]:
    ax, ay, resolved = parse_target(target, session=session, marks_path=marks_path)
    x, y = ax + int(dx), ay + int(dy)
    if not dry_run:
        pyautogui().click(x=x, y=y, clicks=clicks, interval=interval, button=button)
    return {
        "action": "click_near",
        "anchor": {"x": ax, "y": ay},
        "x": x,
        "y": y,
        "dx": int(dx),
        "dy": int(dy),
        "button": button,
        "clicks": clicks,
        "dry_run": dry_run,
        "target": resolved,
    }


def mouse_down(target: str | None = None, *, button: str = "left", session: str = "default", marks_path: Path | None = None, dry_run: bool = False) -> dict[str, Any]:
    x = y = None
    resolved = None
    if target:
        x, y, resolved = parse_target(target, session=session, marks_path=marks_path)
    if not dry_run:
        pyautogui().mouseDown(x=x, y=y, button=button)
    return {"action": "mouse_down", "x": x, "y": y, "button": button, "dry_run": dry_run, "target": resolved}


def mouse_up(target: str | None = None, *, button: str = "left", session: str = "default", marks_path: Path | None = None, dry_run: bool = False) -> dict[str, Any]:
    x = y = None
    resolved = None
    if target:
        x, y, resolved = parse_target(target, session=session, marks_path=marks_path)
    if not dry_run:
        pyautogui().mouseUp(x=x, y=y, button=button)
    return {"action": "mouse_up", "x": x, "y": y, "button": button, "dry_run": dry_run, "target": resolved}


def move(target: str, *, duration: float = 0.0, session: str = "default", marks_path: Path | None = None, dry_run: bool = False) -> dict[str, Any]:
    x, y, resolved = parse_target(target, session=session, marks_path=marks_path)
    if not dry_run:
        pyautogui().moveTo(x, y, duration=duration)
    return {"action": "move", "x": x, "y": y, "duration": duration, "dry_run": dry_run, "target": resolved}


def drag(target: str, *, duration: float = 0.25, button: str = "left", session: str = "default", marks_path: Path | None = None, dry_run: bool = False) -> dict[str, Any]:
    x, y, resolved = parse_target(target, session=session, marks_path=marks_path)
    if not dry_run:
        pyautogui().dragTo(x, y, duration=duration, button=button)
    return {"action": "drag", "x": x, "y": y, "duration": duration, "button": button, "dry_run": dry_run, "target": resolved}


def scroll(amount: int, *, target: str | None = None, session: str = "default", marks_path: Path | None = None, dry_run: bool = False) -> dict[str, Any]:
    resolved: dict[str, Any] | None = None
    x = y = None
    if target:
        x, y, resolved = parse_target(target, session=session, marks_path=marks_path)
    if not dry_run:
        if x is not None and y is not None:
            pyautogui().scroll(amount, x=x, y=y)
        else:
            pyautogui().scroll(amount)
    return {"action": "scroll", "amount": amount, "x": x, "y": y, "dry_run": dry_run, "target": resolved}


def type_text(text: str, *, interval: float = 0.0, dry_run: bool = False) -> dict[str, Any]:
    if not dry_run:
        pyautogui().write(text, interval=interval)
    return {"action": "type", "text_length": len(text), "interval": interval, "dry_run": dry_run}


def hotkey(keys: list[str], *, dry_run: bool = False) -> dict[str, Any]:
    if not dry_run:
        pyautogui().hotkey(*keys)
    return {"action": "hotkey", "keys": keys, "dry_run": dry_run}


def key_down(key: str, *, dry_run: bool = False) -> dict[str, Any]:
    if not dry_run:
        pyautogui().keyDown(key)
    return {"action": "key_down", "key": key, "dry_run": dry_run}


def key_up(key: str, *, dry_run: bool = False) -> dict[str, Any]:
    if not dry_run:
        pyautogui().keyUp(key)
    return {"action": "key_up", "key": key, "dry_run": dry_run}


def press(key: str, *, presses: int = 1, interval: float = 0.0, dry_run: bool = False) -> dict[str, Any]:
    if not dry_run:
        pyautogui().press(key, presses=presses, interval=interval)
    return {"action": "press", "key": key, "presses": presses, "interval": interval, "dry_run": dry_run}


def wait(seconds: float) -> dict[str, Any]:
    time.sleep(seconds)
    return {"action": "wait", "seconds": seconds}


def set_pause(seconds: float) -> dict[str, Any]:
    pg = pyautogui()
    pg.PAUSE = seconds
    return {"action": "pause", "seconds": seconds}


def fail_safe_status(enabled: bool | None = None) -> dict[str, Any]:
    pg = pyautogui()
    if enabled is not None:
        pg.FAILSAFE = enabled
    return {"action": "failsafe", "enabled": bool(pg.FAILSAFE)}


def box_payload(box: Any) -> dict[str, int]:
    return {"left": int(box.left), "top": int(box.top), "width": int(box.width), "height": int(box.height)}


def center_payload(box: Any) -> dict[str, int]:
    return {"x": int(box.left + box.width // 2), "y": int(box.top + box.height // 2)}


def locate_on_screen(image: Path, *, confidence: float | None = None, all_matches: bool = False) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if confidence is not None:
        kwargs["confidence"] = confidence
    pg = pyautogui()
    if all_matches:
        matches = list(pg.locateAllOnScreen(str(image), **kwargs))
        return {
            "found": bool(matches),
            "image": str(image),
            "matches": [{"box": box_payload(match), "center": center_payload(match)} for match in matches],
        }
    result = pg.locateOnScreen(str(image), **kwargs)
    if result is None:
        return {"found": False, "image": str(image)}
    return {"found": True, "image": str(image), "box": box_payload(result), "center": center_payload(result)}


def active_window() -> dict[str, Any]:
    window = pyautogui().getActiveWindow()
    if window is None:
        return {"found": False}
    return {"found": True, "window": window_payload(window)}


def list_windows(title: str | None = None) -> dict[str, Any]:
    pg = pyautogui()
    windows = pg.getWindowsWithTitle(title) if title else pg.getAllWindows()
    return {"windows": [window_payload(window) for window in windows]}


def window_payload(window: Any) -> dict[str, Any]:
    return {
        "title": getattr(window, "title", None),
        "left": int(getattr(window, "left", 0)),
        "top": int(getattr(window, "top", 0)),
        "width": int(getattr(window, "width", 0)),
        "height": int(getattr(window, "height", 0)),
        "is_active": bool(getattr(window, "isActive", False)),
        "is_minimized": bool(getattr(window, "isMinimized", False)),
        "is_maximized": bool(getattr(window, "isMaximized", False)),
    }
