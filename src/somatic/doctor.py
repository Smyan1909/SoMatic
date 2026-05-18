from __future__ import annotations

import importlib.util
import json
import os
import platform
import shutil
import sys
from typing import Any

from .paths import cache_dir, data_dir, legacy_omniparser_dir, onnx_weights_path, onnx_weights_source_file
from .vision_client import health


def check_import(name: str) -> dict[str, Any]:
    return {"name": name, "available": importlib.util.find_spec(name) is not None}


def run_doctor() -> dict[str, Any]:
    checks: list[dict[str, Any]] = [
        {"name": "python", "available": True, "version": sys.version.split()[0], "executable": sys.executable},
        check_import("pyautogui"),
        check_import("PIL"),
        check_import("onnxruntime"),
        check_import("numpy"),
        check_import("huggingface_hub"),
        {"name": "node", "available": shutil.which("node") is not None, "path": shutil.which("node")},
        {"name": "cache_dir", "available": cache_dir().exists(), "path": str(cache_dir())},
        {"name": "data_dir", "available": data_dir().exists(), "path": str(data_dir())},
    ]

    system = platform.system().lower()
    guidance: list[str] = []
    if system == "darwin":
        guidance.append("macOS requires Accessibility and Screen Recording permissions for the terminal or agent host.")
    elif system == "linux":
        guidance.append("Linux works best on X11. Wayland may block screenshots or pointer control depending on compositor policy.")
        guidance.append(f"DISPLAY={os.environ.get('DISPLAY', '')}; WAYLAND_DISPLAY={os.environ.get('WAYLAND_DISPLAY', '')}")
    elif system == "windows":
        guidance.append("Windows automation requires an interactive desktop session; elevated apps may require a matching elevated terminal.")

    onnx_path = onnx_weights_path()
    onnx_check: dict[str, Any] = {
        "name": "yolo_onnx_weights",
        "available": onnx_path.exists(),
        "path": str(onnx_path),
    }
    if onnx_path.exists():
        try:
            onnx_check["size_bytes"] = onnx_path.stat().st_size
        except OSError:
            pass
    provenance_path = onnx_weights_source_file()
    if provenance_path.exists():
        try:
            onnx_check["provenance"] = json.loads(provenance_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    checks.append(onnx_check)

    legacy = legacy_omniparser_dir()
    if legacy.exists():
        guidance.append(
            f"Legacy OmniParser directory present at {legacy}. Run `somatic vision init` to reclaim disk space."
        )

    try:
        vision = health()
        checks.append({"name": "vision_daemon", "available": bool(vision.get("ok")), "details": vision})
    except Exception as exc:
        checks.append({"name": "vision_daemon", "available": False, "error": str(exc)})

    if system == "linux":
        for binary in ("Xvfb", "openbox", "dbus-launch", "xauth", "xdpyinfo", "x11vnc"):
            path = shutil.which(binary)
            checks.append({"name": binary, "available": path is not None, "path": path})
        try:
            from . import headless as _headless

            checks.append({"name": "headless", "available": _headless.is_active(), "details": _headless.status()})
        except Exception as exc:
            checks.append({"name": "headless", "available": False, "error": str(exc)})

    optional = {
        "huggingface_hub", "node", "vision_daemon", "yolo_onnx_weights",
        "Xvfb", "openbox", "dbus-launch", "xauth", "xdpyinfo", "x11vnc", "headless",
    }
    return {
        "system": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": sys.version,
        },
        "checks": checks,
        "guidance": guidance,
        "ready": all(check.get("available", False) for check in checks if check["name"] not in optional),
    }
