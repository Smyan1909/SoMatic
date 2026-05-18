from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .jsonio import fail
from .paths import (
    cache_dir,
    daemon_log_file,
    daemon_pid_file,
    legacy_omniparser_dir,
    onnx_weights_path,
)
from .providers import yolo_onnx

HOST = "127.0.0.1"
PORT = int(os.environ.get("SOMATIC_VISION_PORT", "8765"))
HEALTH_TIMEOUT_DEFAULT = float(os.environ.get("SOMATIC_VISION_INIT_TIMEOUT", "600"))


class DaemonHandler(BaseHTTPRequestHandler):
    session: Any = None
    weights_path: str = ""

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _write_json(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._write_json(200, {
                "ok": True,
                "provider": "yolo-onnx",
                "loaded": DaemonHandler.session is not None,
                "weights_path": DaemonHandler.weights_path,
                "pid": os.getpid(),
            })
            return
        self._write_json(404, {"ok": False, "error": {"code": "not_found", "message": self.path}})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/parse":
            self._write_json(404, {"ok": False, "error": {"code": "not_found", "message": self.path}})
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            self._write_json(400, {"ok": False, "error": {"code": "bad_request", "message": str(exc)}})
            return
        image_path = payload.get("image_path")
        if not image_path:
            self._write_json(400, {"ok": False, "error": {"code": "bad_request", "message": "image_path is required"}})
            return
        path = Path(image_path)
        if not path.exists():
            self._write_json(400, {"ok": False, "error": {"code": "image_not_found", "message": f"{path} does not exist"}})
            return
        if DaemonHandler.session is None:
            self._write_json(503, {"ok": False, "error": {"code": "vision_not_loaded", "message": "Vision daemon has no loaded session."}})
            return
        try:
            result = yolo_onnx.parse(DaemonHandler.session, path)
        except Exception as exc:
            self._write_json(500, {"ok": False, "error": {"code": "yolo_onnx_error", "message": str(exc)}})
            return
        result["ok"] = True
        result["weights_path"] = DaemonHandler.weights_path
        self._write_json(200, result)


def serve(host: str = HOST, port: int = PORT) -> None:
    cleanup_stale_omniparser_dir()
    yolo_onnx.ensure_weights()
    weights = onnx_weights_path()
    DaemonHandler.weights_path = str(weights)
    DaemonHandler.session = yolo_onnx.load_session(weights)
    server = ThreadingHTTPServer((host, port), DaemonHandler)
    daemon_pid_file().write_text(str(os.getpid()), encoding="utf-8")
    try:
        server.serve_forever()
    finally:
        try:
            daemon_pid_file().unlink()
        except FileNotFoundError:
            pass


def is_port_open(host: str = HOST, port: int = PORT) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((host, port)) == 0


def start_daemon(host: str = HOST, port: int = PORT, *, timeout: float = HEALTH_TIMEOUT_DEFAULT) -> dict[str, Any]:
    cleaned = cleanup_stale_omniparser_dir()
    if is_port_open(host, port):
        return {"already_running": True, "url": f"http://{host}:{port}", "cleanup": cleaned}

    log_path = daemon_log_file()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("ab")
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    # Inherit any active headless session env (DISPLAY / XAUTHORITY / D-Bus).
    # When no session is active this is a no-op overlay equivalent to os.environ.
    from . import headless

    proc = subprocess.Popen(
        [sys.executable, "-m", "somatic.vision_daemon", "serve", "--host", host, "--port", str(port)],
        stdout=log,
        stderr=log,
        stdin=subprocess.DEVNULL,
        close_fds=os.name != "nt",
        creationflags=creationflags,
        env=headless.subprocess_env(),
    )
    daemon_pid_file().write_text(str(proc.pid), encoding="utf-8")

    ready = _wait_for_health(host, port, timeout=timeout)
    if not ready["ok"]:
        return {
            "already_running": False,
            "started": False,
            "url": f"http://{host}:{port}",
            "log_path": str(log_path),
            "pid": proc.pid,
            "cleanup": cleaned,
            "error": ready,
        }
    return {
        "already_running": False,
        "started": True,
        "url": f"http://{host}:{port}",
        "log_path": str(log_path),
        "pid": proc.pid,
        "cleanup": cleaned,
        "health": ready["health"],
    }


def stop_daemon() -> dict[str, Any]:
    pid_path = daemon_pid_file()
    if not pid_path.exists():
        return {"stopped": False, "reason": "pid_not_found"}
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except ValueError:
        pid_path.unlink(missing_ok=True)
        return {"stopped": False, "reason": "pid_unreadable"}
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False, capture_output=True)
        else:
            os.kill(pid, signal.SIGTERM)
        return {"stopped": True, "pid": pid}
    finally:
        pid_path.unlink(missing_ok=True)


def cleanup_stale_omniparser_dir() -> dict[str, Any]:
    legacy = legacy_omniparser_dir()
    if not legacy.exists():
        return {"removed": False}
    bytes_freed = 0
    for entry in legacy.rglob("*"):
        if entry.is_file():
            try:
                bytes_freed += entry.stat().st_size
            except OSError:
                pass
    try:
        shutil.rmtree(legacy)
    except Exception as exc:
        return {"removed": False, "error": str(exc), "path": str(legacy)}
    return {"removed": True, "path": str(legacy), "bytes_freed": bytes_freed}


def _wait_for_health(host: str, port: int, *, timeout: float) -> dict[str, Any]:
    from . import vision_client

    deadline = time.time() + timeout
    last_error: str | None = None
    while time.time() < deadline:
        try:
            payload = vision_client.health(server_url=f"http://{host}:{port}")
            return {"ok": True, "health": payload}
        except Exception as exc:
            last_error = str(exc)
            time.sleep(2.0)
    return {"ok": False, "error": last_error or "timeout", "timeout_s": timeout}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="somatic.vision_daemon")
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--host", default=HOST)
    s.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args(argv)
    if args.command == "serve":
        try:
            serve(args.host, args.port)
        except Exception as exc:
            payload = {"ok": False, "error": {"code": "vision_daemon_crash", "message": str(exc)}}
            sys.stderr.write(json.dumps(payload) + "\n")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
