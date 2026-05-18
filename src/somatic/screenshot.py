from __future__ import annotations

import base64
import shutil
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from .automation import pyautogui
from .jsonio import fail
from .marks import normalize_marks, save_marks
from .paths import screenshot_dir
from .vision_client import parse_screenshot


def _read_b64(path: str | Path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def capture_raw(*, output_dir: Path | None = None, input_path: Path | None = None) -> dict[str, Any]:
    target_dir = output_dir or screenshot_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    raw_path = target_dir / f"screenshot-{timestamp}.png"

    if input_path:
        if not input_path.exists():
            fail("screenshot_input_missing", "Input screenshot does not exist.", details={"path": str(input_path)})
        shutil.copyfile(input_path, raw_path)
    else:
        image = pyautogui().screenshot()
        image.save(raw_path)

    with Image.open(raw_path) as image:
        width, height = image.size
    return {"raw_path": str(raw_path), "width": width, "height": height}


def annotate_image(raw_path: Path, marks: list[dict[str, Any]], *, output_dir: Path | None = None) -> str:
    target_dir = output_dir or raw_path.parent
    annotated_path = target_dir / raw_path.name.replace("screenshot-", "annotated-")
    with Image.open(raw_path).convert("RGB") as image:
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()
        for mark in marks:
            x1, y1, x2, y2 = [int(v) for v in mark["bbox"]]
            label = str(mark["id"])
            draw.rectangle((x1, y1, x2, y2), outline=(255, 40, 40), width=3)
            text_bbox = draw.textbbox((x1, y1), label, font=font)
            pad = 3
            draw.rectangle(
                (text_bbox[0] - pad, text_bbox[1] - pad, text_bbox[2] + pad, text_bbox[3] + pad),
                fill=(255, 40, 40),
            )
            draw.text((x1, y1), label, fill=(255, 255, 255), font=font)
        image.save(annotated_path)
    return str(annotated_path)


def screenshot(*, annotate: bool = False, output_dir: Path | None = None, input_path: Path | None = None, session: str = "default", marks_out: Path | None = None, vision_url: str | None = None, include_image_bytes: bool = True) -> dict[str, Any]:
    raw = capture_raw(output_dir=output_dir, input_path=input_path)
    response: dict[str, Any] = {
        "screenshot": {
            "raw_path": raw["raw_path"],
            "width": raw["width"],
            "height": raw["height"],
        }
    }
    if include_image_bytes:
        response["image_b64"] = _read_b64(raw["raw_path"])
        response["image_mime"] = "image/png"

    if not annotate:
        return response

    parsed = parse_screenshot(Path(raw["raw_path"]), server_url=vision_url)
    marks = normalize_marks(parsed.get("marks", []))
    annotated_path = annotate_image(Path(raw["raw_path"]), marks, output_dir=output_dir)

    mark_map = {
        "version": 1,
        "session": session,
        "source_image": raw["raw_path"],
        "annotated_image": annotated_path,
        "width": raw["width"],
        "height": raw["height"],
        "marks": marks,
        "provider": parsed.get("provider", "yolo-onnx"),
        "inference_ms": parsed.get("inference_ms"),
    }
    saved_path = save_marks(mark_map, session=session, path=marks_out)
    response["screenshot"]["annotated_path"] = annotated_path
    response["marks_path"] = str(saved_path)
    response["marks"] = marks
    response["provider"] = mark_map["provider"]
    response["inference_ms"] = mark_map["inference_ms"]
    if include_image_bytes:
        response["annotated_image_b64"] = _read_b64(annotated_path)
        response["annotated_image_mime"] = "image/png"
    return response
