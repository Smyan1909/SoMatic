from __future__ import annotations

import json
import sys
import time
import traceback
from collections.abc import Callable
from typing import Any


class SomaticError(Exception):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True), flush=True)


def command_response(command: str, func: Callable[[], dict[str, Any]]) -> int:
    started = time.perf_counter()
    try:
        result = func()
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        emit({"ok": True, "command": command, "elapsed_ms": elapsed_ms, **result})
        return 0
    except SomaticError as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        emit({
            "ok": False,
            "command": command,
            "elapsed_ms": elapsed_ms,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        })
        return 2
    except Exception as exc:  # pragma: no cover - defensive envelope
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        emit({
            "ok": False,
            "command": command,
            "elapsed_ms": elapsed_ms,
            "error": {
                "code": "unexpected_error",
                "message": str(exc),
                "traceback": traceback.format_exc().splitlines(),
            },
        })
        return 1


def fail(code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
    raise SomaticError(code, message, details=details)


def write_stderr(message: str) -> None:
    print(message, file=sys.stderr)
