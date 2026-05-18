from __future__ import annotations

import json

from somatic.automation import parse_target
from somatic.marks import get_mark, save_marks


def test_save_and_resolve_mark(tmp_path):
    marks_path = tmp_path / "marks.json"
    save_marks({
        "version": 1,
        "marks": [{"id": 7, "bbox": [10, 20, 30, 40], "center": [20, 30]}],
    }, path=marks_path)

    mark = get_mark(7, path=marks_path)

    assert mark.center == (20, 30)


def test_parse_coordinate_target():
    x, y, resolved = parse_target("12,34")

    assert (x, y) == (12, 34)
    assert resolved["source"] == "coordinate"


def test_parse_mark_target(tmp_path):
    marks_path = tmp_path / "marks.json"
    marks_path.write_text(json.dumps({"marks": [{"id": 1, "bbox": [0, 0, 10, 20]}]}), encoding="utf-8")

    x, y, resolved = parse_target("1", marks_path=marks_path)

    assert (x, y) == (5, 10)
    assert resolved["source"] == "mark"
