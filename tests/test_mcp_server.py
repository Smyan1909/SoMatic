from __future__ import annotations

import base64

import pytest

pytest.importorskip("mcp")
pytest.importorskip("numpy")
from PIL import Image as PILImage  # noqa: E402

from somatic import mcp_server  # noqa: E402


def _fake_screenshot_result(annotated_path):
    return {
        "screenshot": {
            "raw_path": "/tmp/raw.png",
            "annotated_path": str(annotated_path),
            "width": 40,
            "height": 30,
        },
        "marks": [
            {"id": 1, "bbox": [0, 0, 10, 10], "center": [5, 5], "confidence": 0.9, "source": "yolo-onnx", "interactable": True}
        ],
        "marks_path": "/tmp/marks.json",
        "provider": "yolo-onnx",
        "inference_ms": 5.0,
        "image_b64": base64.b64encode(b"raw-bytes").decode("ascii"),
        "image_mime": "image/png",
        "annotated_image_b64": base64.b64encode(annotated_path.read_bytes()).decode("ascii"),
        "annotated_image_mime": "image/png",
    }


def test_screenshot_annotated_returns_image_and_text(monkeypatch, tmp_path):
    annotated = tmp_path / "annotated-test.png"
    PILImage.new("RGB", (40, 30), (255, 255, 255)).save(annotated)

    monkeypatch.setattr(mcp_server, "_screenshot", lambda **kw: _fake_screenshot_result(annotated))

    # Call the underlying function (FastMCP wraps tools; .fn is the raw callable).
    fn = mcp_server.screenshot_annotated.fn if hasattr(mcp_server.screenshot_annotated, "fn") else mcp_server.screenshot_annotated
    result = fn()

    assert isinstance(result, list)
    image_blocks = [c for c in result if getattr(c, "type", None) == "image"]
    text_blocks = [c for c in result if getattr(c, "type", None) == "text"]
    assert len(image_blocks) == 1
    assert len(text_blocks) == 1
    assert image_blocks[0].mimeType == "image/png"
    assert image_blocks[0].data  # non-empty base64
    # Text block must NOT contain the duplicated base64 bytes.
    assert "annotated_image_b64" not in text_blocks[0].text
    assert "image_b64" not in text_blocks[0].text
    # Marks should still be there
    assert "marks" in text_blocks[0].text


def test_screenshot_returns_raw_image_and_text(monkeypatch, tmp_path):
    raw = tmp_path / "raw-only.png"
    PILImage.new("RGB", (40, 30), (0, 0, 0)).save(raw)

    def fake(**kw):
        # annotate=False path: no annotated_image_b64
        return {
            "screenshot": {"raw_path": str(raw), "width": 40, "height": 30},
            "image_b64": base64.b64encode(raw.read_bytes()).decode("ascii"),
            "image_mime": "image/png",
        }

    monkeypatch.setattr(mcp_server, "_screenshot", fake)
    fn = mcp_server.screenshot.fn if hasattr(mcp_server.screenshot, "fn") else mcp_server.screenshot
    result = fn()

    assert any(getattr(c, "type", None) == "image" for c in result)
    text = next(c for c in result if getattr(c, "type", None) == "text").text
    assert "image_b64" not in text


def test_skill_prompt_returns_full_text():
    fn = mcp_server.skill_prompt.fn if hasattr(mcp_server.skill_prompt, "fn") else mcp_server.skill_prompt
    text = fn()
    assert "Operating Loop" in text
    assert "click_near" in text or "click-near" in text


def test_instructions_includes_workflow_hint():
    # FastMCP exposes instructions via the underlying server config.
    instructions = mcp_server.mcp.instructions or ""
    assert "vision_init" in instructions
    assert "screenshot_annotated" in instructions
