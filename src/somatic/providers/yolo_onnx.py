"""
YOLO ONNX inference provider — MIT-licensed.

This module imports ONLY MIT/BSD-licensed dependencies (onnxruntime, numpy,
huggingface_hub, Pillow). It deliberately does NOT import `ultralytics` or
any AGPL-licensed package; the AGPL-3.0 boundary for SoMatic lives in the
`tools/` directory at the repo root.

The conversion path (`.pt` → `.onnx`) is intentionally NOT available here.
If no pre-converted ONNX is reachable, `ensure_weights()` returns a clear
error pointing the user at three resolution paths (env vars or `tools/`),
none of which loads AGPL code into this process.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from ..jsonio import fail
from ..paths import onnx_weights_path, onnx_weights_source_file

HF_ONNX_REPO_ID = os.environ.get("SOMATIC_YOLO_ONNX_REPO", "Smyan-Sondur/somatic-icon-detect")
HF_ONNX_FILENAME = os.environ.get("SOMATIC_YOLO_ONNX_FILENAME", "icon-detect.onnx")

INPUT_SIZE = int(os.environ.get("SOMATIC_YOLO_INPUT_SIZE", "640"))
# Confidence threshold. 0.05 matches OmniParser's upstream default and gives
# ~63% coverage on ScreenSpot-Pro vs. ~47% at 0.10 (measured 2026-05-XX on
# the icon_detect ONNX). Lower thresholds (0.02–0.03) push coverage higher
# but flood dense UIs with marks the VLM has to disambiguate without text
# captions. Tunable via env var if you want to experiment.
CONF_THRESH = float(os.environ.get("SOMATIC_YOLO_CONF", "0.05"))
IOU_THRESH = float(os.environ.get("SOMATIC_YOLO_IOU", "0.45"))
LETTERBOX_FILL = (114, 114, 114)


def ensure_weights(target_path: Path | None = None) -> dict[str, Any]:
    """Resolve YOLO ONNX weights without ever loading AGPL code.

    Resolution order:
      1. If the target file already exists, return it.
      2. If `SOMATIC_YOLO_ONNX_PATH` points at a readable file, copy it.
      3. If `SOMATIC_YOLO_ONNX_REPO` is set, download the ONNX from that HF
         repo and verify it against the sidecar `<filename>.sha256` (if the
         sidecar exists in the repo).

    If none of those resolve, fail with `yolo_onnx_unavailable` and an error
    message that documents all three options plus the AGPL-licensed
    conversion tool at `tools/convert_yolo_to_onnx.py`. We deliberately do
    NOT invoke that tool from here — it lives outside the MIT package.
    """
    target = target_path or onnx_weights_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        provenance = _read_provenance()
        return {"path": str(target), "downloaded": False, **provenance}

    override = os.environ.get("SOMATIC_YOLO_ONNX_PATH")
    if override:
        src = Path(override)
        if not src.exists():
            fail(
                "yolo_onnx_missing",
                f"SOMATIC_YOLO_ONNX_PATH points at {src} which does not exist.",
                details={"path": str(src)},
            )
        shutil.copyfile(src, target)
        digest = _hash_file(target)
        _write_provenance(source="env_override", details={"copied_from": str(src), "sha256": digest})
        return {"path": str(target), "downloaded": True, "source": "env_override", "sha256": digest}

    if HF_ONNX_REPO_ID:
        hf_path = _hf_download(HF_ONNX_REPO_ID, HF_ONNX_FILENAME)
        if hf_path is not None:
            verification = _verify_sha256_sidecar(
                HF_ONNX_REPO_ID, HF_ONNX_FILENAME, hf_path,
            )
            shutil.copyfile(hf_path, target)
            digest = _hash_file(target)
            _write_provenance(
                source="hf_onnx",
                details={
                    "repo": HF_ONNX_REPO_ID,
                    "filename": HF_ONNX_FILENAME,
                    "sha256": digest,
                    "sha256_verified": verification,
                },
            )
            return {
                "path": str(target),
                "downloaded": True,
                "source": "hf_onnx",
                "repo": HF_ONNX_REPO_ID,
                "sha256": digest,
                "sha256_verified": verification,
            }

    fail(
        "yolo_onnx_unavailable",
        (
            "No pre-converted YOLO ONNX is available. Resolve one of:\n"
            "  1. Set SOMATIC_YOLO_ONNX_REPO=<hf-repo-id> to download a "
            "published .onnx (recommended once SoMatic publishes one).\n"
            "  2. Set SOMATIC_YOLO_ONNX_PATH=/path/to/icon-detect.onnx pointing "
            "at a local .onnx you already have.\n"
            "  3. Generate one yourself using the AGPL-licensed conversion "
            "tool at tools/convert_yolo_to_onnx.py (see tools/README.md). "
            "Note: that tool imports ultralytics (AGPL-3.0) and its output is "
            "AGPL-licensed. The SoMatic CLI is MIT and does not invoke it."
        ),
        details={
            "repo_env": "SOMATIC_YOLO_ONNX_REPO",
            "path_env": "SOMATIC_YOLO_ONNX_PATH",
            "tools_path": "tools/convert_yolo_to_onnx.py",
        },
    )
    raise AssertionError("unreachable")


def load_session(weights_path: Path | None = None):
    try:
        import onnxruntime as ort  # type: ignore
    except Exception as exc:
        fail(
            "onnxruntime_missing",
            "onnxruntime is not installed. Install with `pip install -e .[vision]`.",
            details={"error": str(exc)},
        )

    path = weights_path or onnx_weights_path()
    if not path.exists():
        fail("yolo_onnx_missing", f"ONNX weights not found at {path}. Run `somatic vision init` first.", details={"path": str(path)})

    sess_options = ort.SessionOptions()
    threads_env = os.environ.get("SOMATIC_YOLO_THREADS")
    if threads_env:
        try:
            threads = max(1, int(threads_env))
            sess_options.intra_op_num_threads = threads
        except ValueError:
            pass
    providers = ["CPUExecutionProvider"]
    return ort.InferenceSession(str(path), sess_options=sess_options, providers=providers)


def letterbox(image: Image.Image, size: int = INPUT_SIZE) -> tuple[np.ndarray, float, tuple[int, int]]:
    orig_w, orig_h = image.size
    scale = min(size / orig_w, size / orig_h)
    new_w = int(round(orig_w * scale))
    new_h = int(round(orig_h * scale))
    pad_x = (size - new_w) // 2
    pad_y = (size - new_h) // 2

    resized = image.resize((new_w, new_h), Image.BILINEAR)
    canvas = Image.new("RGB", (size, size), LETTERBOX_FILL)
    canvas.paste(resized, (pad_x, pad_y))

    arr = np.asarray(canvas, dtype=np.float32) / 255.0  # HWC, RGB, [0,1]
    arr = np.transpose(arr, (2, 0, 1))  # CHW
    return arr, scale, (pad_x, pad_y)


def nms(boxes: np.ndarray, scores: np.ndarray, iou_thresh: float) -> list[int]:
    if boxes.size == 0:
        return []
    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]
    areas = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    order = scores.argsort()[::-1]

    keep: list[int] = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(x1[i], x1[rest])
        yy1 = np.maximum(y1[i], y1[rest])
        xx2 = np.minimum(x2[i], x2[rest])
        yy2 = np.minimum(y2[i], y2[rest])
        inter_w = np.maximum(0.0, xx2 - xx1)
        inter_h = np.maximum(0.0, yy2 - yy1)
        inter = inter_w * inter_h
        union = areas[i] + areas[rest] - inter
        iou = np.where(union > 0, inter / union, 0.0)
        order = rest[iou <= iou_thresh]
    return keep


def parse(session, image_path: Path, *, conf_thresh: float | None = None, iou_thresh: float | None = None) -> dict[str, Any]:
    conf = CONF_THRESH if conf_thresh is None else conf_thresh
    iou = IOU_THRESH if iou_thresh is None else iou_thresh

    with Image.open(image_path) as img:
        rgb = img.convert("RGB")
        orig_w, orig_h = rgb.size
        tensor, scale, (pad_x, pad_y) = letterbox(rgb, INPUT_SIZE)

    input_name = session.get_inputs()[0].name
    started = time.perf_counter()
    outputs = session.run(None, {input_name: tensor[np.newaxis, ...].astype(np.float32)})
    inference_ms = round((time.perf_counter() - started) * 1000, 2)

    raw = outputs[0]  # Ultralytics YOLOv8 ONNX: (1, 4+nc, N)
    if raw.ndim != 3:
        fail("yolo_onnx_bad_output", f"Unexpected ONNX output rank {raw.ndim}; expected 3.", details={"shape": list(raw.shape)})
    raw = raw[0]                  # (4+nc, N)
    raw = raw.transpose(1, 0)     # (N, 4+nc)

    if raw.shape[1] < 5:
        fail("yolo_onnx_bad_output", "ONNX output has fewer than 5 channels.", details={"shape": list(raw.shape)})

    boxes_xywh = raw[:, :4]
    class_scores = raw[:, 4:]
    scores = class_scores.max(axis=1) if class_scores.shape[1] > 0 else np.ones(raw.shape[0], dtype=np.float32)

    keep_conf = scores >= conf
    if not np.any(keep_conf):
        return {
            "provider": "yolo-onnx",
            "marks": [],
            "inference_ms": inference_ms,
            "conf_threshold": conf,
            "iou_threshold": iou,
            "image_size": [orig_w, orig_h],
        }

    boxes_xywh = boxes_xywh[keep_conf]
    scores = scores[keep_conf]

    cx, cy, w, h = boxes_xywh[:, 0], boxes_xywh[:, 1], boxes_xywh[:, 2], boxes_xywh[:, 3]
    x1 = cx - w / 2.0
    y1 = cy - h / 2.0
    x2 = cx + w / 2.0
    y2 = cy + h / 2.0
    boxes_xyxy = np.stack([x1, y1, x2, y2], axis=1)

    keep_idx = nms(boxes_xyxy, scores, iou)
    boxes_xyxy = boxes_xyxy[keep_idx]
    scores = scores[keep_idx]

    boxes_xyxy[:, [0, 2]] -= pad_x
    boxes_xyxy[:, [1, 3]] -= pad_y
    boxes_xyxy /= scale
    boxes_xyxy[:, [0, 2]] = np.clip(boxes_xyxy[:, [0, 2]], 0, orig_w)
    boxes_xyxy[:, [1, 3]] = np.clip(boxes_xyxy[:, [1, 3]], 0, orig_h)

    pairs = [(boxes_xyxy[i], float(scores[i])) for i in range(boxes_xyxy.shape[0])]
    pairs.sort(key=lambda item: (round(float(item[0][1]) / 24.0), float(item[0][0])))

    marks: list[dict[str, Any]] = []
    for index, (box, score) in enumerate(pairs, start=1):
        x1f, y1f, x2f, y2f = box.tolist()
        x1i, y1i, x2i, y2i = int(round(x1f)), int(round(y1f)), int(round(x2f)), int(round(y2f))
        if x2i <= x1i or y2i <= y1i:
            continue
        marks.append({
            "id": index,
            "bbox": [x1i, y1i, x2i, y2i],
            "center": [(x1i + x2i) // 2, (y1i + y2i) // 2],
            "confidence": round(score, 4),
            "source": "yolo-onnx",
            "interactable": True,
        })

    for new_id, mark in enumerate(marks, start=1):
        mark["id"] = new_id

    return {
        "provider": "yolo-onnx",
        "marks": marks,
        "inference_ms": inference_ms,
        "conf_threshold": conf,
        "iou_threshold": iou,
        "image_size": [orig_w, orig_h],
    }


def _hf_download(repo_id: str, filename: str) -> Path | None:
    try:
        from huggingface_hub import hf_hub_download
    except Exception:
        return None
    try:
        path = hf_hub_download(repo_id=repo_id, filename=filename)
    except Exception:
        return None
    return Path(path)


def _verify_sha256_sidecar(repo_id: str, filename: str, downloaded: Path) -> dict[str, Any]:
    """Try to fetch `<filename>.sha256` from the same HF repo and compare.

    Returns a dict describing the verification result. Missing sidecar is NOT
    fatal (returns `{"checked": False, "reason": "sidecar_missing"}`) so dev
    iteration isn't blocked by sha files lagging the model. A mismatch IS
    fatal — we raise `yolo_onnx_sha_mismatch` rather than silently using
    tampered weights.
    """
    sidecar_path = _hf_download(repo_id, f"{filename}.sha256")
    if sidecar_path is None:
        return {"checked": False, "reason": "sidecar_missing"}

    try:
        sidecar_text = Path(sidecar_path).read_text(encoding="utf-8").strip()
    except OSError as exc:
        return {"checked": False, "reason": "sidecar_unreadable", "error": str(exc)}

    expected = sidecar_text.split()[0].strip().lower() if sidecar_text else ""
    actual = _hash_file(downloaded).lower()
    if not expected:
        return {"checked": False, "reason": "sidecar_empty"}
    if expected != actual:
        fail(
            "yolo_onnx_sha_mismatch",
            f"SHA256 mismatch for downloaded {filename}: sidecar says {expected}, "
            f"file hashes to {actual}. Refusing to install possibly-tampered weights.",
            details={"expected": expected, "actual": actual, "repo": repo_id, "filename": filename},
        )
    return {"checked": True, "sha256": actual, "sidecar": f"{filename}.sha256"}


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_provenance(*, source: str, details: dict[str, Any]) -> None:
    payload = {"source": source, "details": details, "timestamp": time.time()}
    onnx_weights_source_file().write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _read_provenance() -> dict[str, Any]:
    path = onnx_weights_source_file()
    if not path.exists():
        return {}
    try:
        return {"provenance": json.loads(path.read_text(encoding="utf-8"))}
    except Exception:
        return {}
