from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")
from PIL import Image

from somatic.providers import yolo_onnx


def test_letterbox_preserves_aspect_and_pads_correctly():
    image = Image.new("RGB", (200, 100), (10, 20, 30))
    tensor, scale, (pad_x, pad_y) = yolo_onnx.letterbox(image, size=640)

    assert tensor.shape == (3, 640, 640)
    assert tensor.dtype == np.float32
    # 200x100 → scale by 640/200 = 3.2 → fits 640x320 with vertical pad of 160
    assert scale == pytest.approx(3.2, rel=1e-3)
    assert pad_x == 0
    assert pad_y == 160

    # Padded rows should be the gray fill value (114/255).
    expected_fill = 114 / 255.0
    assert tensor[0, 0, 0] == pytest.approx(expected_fill, abs=1e-3)
    assert tensor[0, 639, 0] == pytest.approx(expected_fill, abs=1e-3)
    # Center should be the original image colour scaled to [0,1].
    assert tensor[0, 320, 320] == pytest.approx(10 / 255.0, abs=1e-2)
    assert tensor[1, 320, 320] == pytest.approx(20 / 255.0, abs=1e-2)
    assert tensor[2, 320, 320] == pytest.approx(30 / 255.0, abs=1e-2)


def test_nms_drops_overlapping_boxes():
    boxes = np.array([
        [0, 0, 10, 10],
        [1, 1, 11, 11],   # heavily overlaps with the first
        [50, 50, 60, 60],  # disjoint
    ], dtype=np.float32)
    scores = np.array([0.9, 0.8, 0.7], dtype=np.float32)

    keep = yolo_onnx.nms(boxes, scores, iou_thresh=0.45)

    assert sorted(keep) == [0, 2]


def test_nms_handles_empty():
    assert yolo_onnx.nms(np.zeros((0, 4)), np.zeros((0,)), iou_thresh=0.5) == []


class _FakeInput:
    name = "images"


class _FakeSession:
    def __init__(self, raw_output: np.ndarray) -> None:
        self._raw = raw_output

    def get_inputs(self) -> list[_FakeInput]:
        return [_FakeInput()]

    def run(self, _outputs, _feeds):
        return [self._raw]


def test_parse_rescales_boxes_to_original_image(tmp_path):
    image_path = tmp_path / "screenshot-test.png"
    Image.new("RGB", (320, 160), (200, 200, 200)).save(image_path)

    # Ultralytics YOLOv8 ONNX canonical shape: (1, 4+nc, N).
    # 320x160 source → letterbox scale 2.0, pad_y = 160.
    # Place a 100x60 box centred at canvas (320, 320) which back-maps to original
    # (160, 80) i.e. the centre of the source image.
    raw = np.zeros((1, 5, 1), dtype=np.float32)
    raw[0, :, 0] = [320.0, 320.0, 100.0, 60.0, 0.92]

    session = _FakeSession(raw)
    result = yolo_onnx.parse(session, image_path, conf_thresh=0.5, iou_thresh=0.5)

    assert result["provider"] == "yolo-onnx"
    assert result["image_size"] == [320, 160]
    assert len(result["marks"]) == 1
    mark = result["marks"][0]
    assert mark["id"] == 1
    x1, y1, x2, y2 = mark["bbox"]
    # Original coords: cx=160, cy=80, w=50, h=30 → x1=135,y1=65,x2=185,y2=95
    assert (x1, y1, x2, y2) == (135, 65, 185, 95)
    assert mark["center"] == [160, 80]
    assert mark["confidence"] == pytest.approx(0.92, abs=1e-3)
    assert mark["source"] == "yolo-onnx"
    assert mark["interactable"] is True


def test_parse_filters_below_confidence(tmp_path):
    image_path = tmp_path / "screenshot-test.png"
    Image.new("RGB", (320, 160), (200, 200, 200)).save(image_path)

    raw = np.zeros((1, 5, 1), dtype=np.float32)
    raw[0, :, 0] = [100.0, 100.0, 10.0, 10.0, 0.05]
    session = _FakeSession(raw)

    result = yolo_onnx.parse(session, image_path, conf_thresh=0.5)

    assert result["marks"] == []


def test_parse_sorts_top_to_bottom_left_to_right(tmp_path):
    image_path = tmp_path / "screenshot-test.png"
    Image.new("RGB", (320, 320), (200, 200, 200)).save(image_path)

    # Three boxes in canvas space. 320x320 → scale 2.0, pad 0,0 → canvas == original
    # (after halving). Canvas centres: (100, 500), (500, 100), (100, 100) →
    # original centres: (50, 250), (250, 50), (50, 50).
    raw = np.zeros((1, 5, 3), dtype=np.float32)
    raw[0, :, 0] = [100.0, 500.0, 40.0, 40.0, 0.9]  # bottom-left after rescale
    raw[0, :, 1] = [500.0, 100.0, 40.0, 40.0, 0.9]  # top-right after rescale
    raw[0, :, 2] = [100.0, 100.0, 40.0, 40.0, 0.9]  # top-left after rescale
    session = _FakeSession(raw)

    result = yolo_onnx.parse(session, image_path, conf_thresh=0.5, iou_thresh=0.9)

    ids = [m["id"] for m in result["marks"]]
    centers = [tuple(m["center"]) for m in result["marks"]]
    assert ids == [1, 2, 3]
    # Sorted top-to-bottom then left-to-right after rescale (canvas == original here).
    assert centers == [(50, 50), (250, 50), (50, 250)]
