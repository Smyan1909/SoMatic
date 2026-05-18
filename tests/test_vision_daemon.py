from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

pytest.importorskip("numpy")
from PIL import Image

from somatic import vision_daemon


class _FakeSession:
    """Stand-in for an onnxruntime.InferenceSession."""


def _start_test_server(weights_path: str, parse_result: dict) -> tuple[ThreadingHTTPServer, threading.Thread]:
    vision_daemon.DaemonHandler.session = _FakeSession()
    vision_daemon.DaemonHandler.weights_path = weights_path
    server = ThreadingHTTPServer(("127.0.0.1", 0), vision_daemon.DaemonHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post_json(url: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_health_reports_loaded_session(tmp_path, monkeypatch):
    server, _ = _start_test_server(str(tmp_path / "icon-detect.onnx"), {})
    try:
        payload = _get_json(f"http://127.0.0.1:{server.server_port}/health")
        assert payload["ok"] is True
        assert payload["loaded"] is True
        assert payload["provider"] == "yolo-onnx"
    finally:
        server.shutdown()
        server.server_close()
        vision_daemon.DaemonHandler.session = None


def test_parse_invokes_provider(tmp_path, monkeypatch):
    image_path = tmp_path / "screenshot-test.png"
    Image.new("RGB", (40, 30), (255, 255, 255)).save(image_path)

    expected = {
        "provider": "yolo-onnx",
        "marks": [{"id": 1, "bbox": [0, 0, 10, 10], "center": [5, 5], "confidence": 0.9, "source": "yolo-onnx", "interactable": True}],
        "inference_ms": 1.0,
        "conf_threshold": 0.1,
        "iou_threshold": 0.45,
        "image_size": [40, 30],
    }

    def fake_parse(session, path):
        assert isinstance(session, _FakeSession)
        assert Path(path) == image_path
        return dict(expected)

    monkeypatch.setattr(vision_daemon.yolo_onnx, "parse", fake_parse)

    server, _ = _start_test_server(str(tmp_path / "icon-detect.onnx"), expected)
    try:
        status, payload = _post_json(f"http://127.0.0.1:{server.server_port}/parse", {"image_path": str(image_path)})
        assert status == 200
        assert payload["ok"] is True
        assert payload["provider"] == "yolo-onnx"
        assert payload["marks"][0]["bbox"] == [0, 0, 10, 10]
        assert payload["weights_path"].endswith("icon-detect.onnx")
    finally:
        server.shutdown()
        server.server_close()
        vision_daemon.DaemonHandler.session = None


def test_parse_missing_image_returns_400(tmp_path):
    server, _ = _start_test_server(str(tmp_path / "icon-detect.onnx"), {})
    try:
        status, payload = _post_json(f"http://127.0.0.1:{server.server_port}/parse", {"image_path": str(tmp_path / "nope.png")})
        assert status == 400
        assert payload["ok"] is False
        assert payload["error"]["code"] == "image_not_found"
    finally:
        server.shutdown()
        server.server_close()
        vision_daemon.DaemonHandler.session = None


def test_cleanup_stale_omniparser_dir_removes_legacy(tmp_path, monkeypatch):
    monkeypatch.setenv("SOMATIC_DATA_DIR", str(tmp_path))
    from somatic import paths as paths_module
    legacy = paths_module.legacy_omniparser_dir()
    legacy.mkdir(parents=True, exist_ok=True)
    (legacy / "weights").mkdir()
    (legacy / "weights" / "model.pt").write_bytes(b"x" * 1024)

    result = vision_daemon.cleanup_stale_omniparser_dir()

    assert result["removed"] is True
    assert result["bytes_freed"] >= 1024
    assert not legacy.exists()


def test_cleanup_no_op_when_no_legacy(tmp_path, monkeypatch):
    monkeypatch.setenv("SOMATIC_DATA_DIR", str(tmp_path))
    result = vision_daemon.cleanup_stale_omniparser_dir()
    assert result == {"removed": False}
