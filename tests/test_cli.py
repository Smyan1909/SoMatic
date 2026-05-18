from __future__ import annotations

import json

from somatic.cli import main


def test_wait_outputs_json(capsys):
    exit_code = main(["wait", "0"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["command"] == "wait"
    assert payload["action"] == "wait"


def test_click_dry_run_coordinate(capsys):
    exit_code = main(["click", "10,20", "--dry-run"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["x"] == 10
    assert payload["y"] == 20
    assert payload["dry_run"] is True


def test_right_click_dry_run_coordinate(capsys):
    exit_code = main(["right-click", "10,20", "--dry-run"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["button"] == "right"
    assert payload["clicks"] == 1


def test_mouse_down_dry_run_without_target(capsys):
    exit_code = main(["mouse-down", "--dry-run"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["action"] == "mouse_down"
    assert payload["target"] is None


def test_vision_status_when_daemon_down(capsys, monkeypatch):
    monkeypatch.setenv("SOMATIC_VISION_URL", "http://127.0.0.1:1")
    exit_code = main(["vision", "status", "--url", "http://127.0.0.1:1"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["command"] == "vision status"
    assert payload["running"] is False
    assert payload["error"]["code"] == "vision_unavailable"


def test_click_near_dry_run_with_coordinate(capsys):
    exit_code = main(["click-near", "100,200", "--dx", "30", "--dy", "-10", "--dry-run"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["action"] == "click_near"
    assert payload["anchor"] == {"x": 100, "y": 200}
    assert payload["x"] == 130 and payload["y"] == 190


def test_skill_command_returns_text(capsys):
    exit_code = main(["skill"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["ok"] is True
    assert "text" in payload
    assert "Operating Loop" in payload["text"]
    assert "click_near" in payload["text"] or "click-near" in payload["text"]


def test_screenshot_no_image_flag_omits_b64(capsys, tmp_path):
    # Provide an input file so we don't actually capture the desktop; this
    # exercises the screenshot pipeline with --no-image opted in.
    from PIL import Image
    src = tmp_path / "in.png"
    Image.new("RGB", (32, 24), (255, 255, 255)).save(src)

    exit_code = main(["screenshot", "--input", str(src), "--output-dir", str(tmp_path), "--no-image"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["ok"] is True
    assert "image_b64" not in payload
    assert "annotated_image_b64" not in payload


def test_screenshot_includes_b64_by_default(capsys, tmp_path):
    from PIL import Image
    src = tmp_path / "in.png"
    Image.new("RGB", (32, 24), (255, 255, 255)).save(src)

    exit_code = main(["screenshot", "--input", str(src), "--output-dir", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["ok"] is True
    assert "image_b64" in payload and len(payload["image_b64"]) > 0
    assert payload["image_mime"] == "image/png"
