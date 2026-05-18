from __future__ import annotations

from PIL import Image

from somatic.screenshot import annotate_image


def test_annotate_image_draws_output(tmp_path):
    raw = tmp_path / "screenshot-test.png"
    Image.new("RGB", (100, 80), (255, 255, 255)).save(raw)

    annotated = annotate_image(raw, [{"id": 1, "bbox": [10, 10, 50, 40]}], output_dir=tmp_path)

    assert (tmp_path / "annotated-test.png").exists()
    assert annotated.endswith("annotated-test.png")
