from __future__ import annotations

import json

from somatic import automation


def test_click_near_with_coordinate_target_applies_offset():
    result = automation.click_near("100,200", dx=30, dy=-10, dry_run=True)

    assert result["action"] == "click_near"
    assert result["anchor"] == {"x": 100, "y": 200}
    assert result["x"] == 130
    assert result["y"] == 190
    assert result["dx"] == 30
    assert result["dy"] == -10
    assert result["dry_run"] is True
    assert result["target"] == {"source": "coordinate"}


def test_click_near_with_mark_id_resolves_then_offsets(tmp_path):
    marks_path = tmp_path / "marks.json"
    marks_path.write_text(json.dumps({"marks": [{"id": 5, "bbox": [0, 0, 40, 40], "center": [20, 20]}]}), encoding="utf-8")

    result = automation.click_near("5", dx=300, dy=0, dry_run=True, marks_path=marks_path)

    assert result["anchor"] == {"x": 20, "y": 20}
    assert result["x"] == 320
    assert result["y"] == 20
    assert result["target"]["source"] == "mark"


def test_click_near_zero_offset_matches_click_target():
    # With dx=dy=0 the click point equals the anchor — a no-op fallback that
    # behaves like a regular click while still recording the action shape.
    result = automation.click_near("50,60", dry_run=True)
    assert result["anchor"] == {"x": 50, "y": 60}
    assert result["x"] == 50
    assert result["y"] == 60
    assert result["dx"] == 0
    assert result["dy"] == 0
