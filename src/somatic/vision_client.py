from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .jsonio import fail

DEFAULT_VISION_URL = "http://127.0.0.1:8765"


def vision_url(explicit: str | None = None) -> str:
    return explicit or os.environ.get("SOMATIC_VISION_URL", DEFAULT_VISION_URL)


def request_json(path: str, payload: dict[str, Any] | None = None, *, server_url: str | None = None, timeout: float = 30.0) -> dict[str, Any]:
    url = vision_url(server_url).rstrip("/") + path
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if payload is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            details = json.loads(exc.read().decode("utf-8"))
        except Exception:
            details = {"body": str(exc)}
        fail(
            details.get("error", {}).get("code", "vision_http_error"),
            details.get("error", {}).get("message", "The vision daemon returned an error."),
            details=details,
        )
    except urllib.error.URLError as exc:
        fail(
            "vision_unavailable",
            "The local SoMatic vision daemon is not reachable. Run `somatic vision init` first, or use `somatic screenshot` without `--annotate`.",
            details={"url": url, "error": str(exc)},
        )
    raise AssertionError("unreachable")


def parse_screenshot(image_path: Path, *, server_url: str | None = None) -> dict[str, Any]:
    return request_json("/parse", {"image_path": str(image_path)}, server_url=server_url, timeout=180.0)


def health(*, server_url: str | None = None) -> dict[str, Any]:
    return request_json("/health", server_url=server_url, timeout=5.0)
