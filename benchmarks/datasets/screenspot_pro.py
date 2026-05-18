"""ScreenSpot-Pro loader.

HF dataset: `likaixin/ScreenSpot-Pro` (MIT). Each sample has an image, an
instruction, a bbox in absolute pixel coordinates, and metadata (platform,
application, group, instruction_style).

We normalise bboxes to [0,1] at load time so the agent layer is dataset-
agnostic.
"""
from __future__ import annotations

import io
import os
from collections.abc import Iterator
from typing import Any

from ..common.sampling import load_or_create_subset
from ..common.types import GroundingTask

DATASET_NAME = "screenspot-pro"
HF_REPO = os.environ.get("SOMATIC_BENCH_SCREENSPOT_PRO_REPO", "likaixin/ScreenSpot-Pro")
SUBSET_N = 200
STRATA = ("platform", "group")


def _bbox_to_normalised(
    bbox: list[float], width: int, height: int
) -> tuple[float, float, float, float] | None:
    if bbox is None or len(bbox) != 4:
        return None
    x1, y1, x2, y2 = bbox
    # ScreenSpot-Pro emits absolute pixel coords.
    return (
        max(0.0, x1 / width),
        max(0.0, y1 / height),
        min(1.0, x2 / width),
        min(1.0, y2 / height),
    )


def _to_task(sample: dict[str, Any], index: int) -> GroundingTask | None:
    image = sample.get("image")
    if image is None:
        return None
    if hasattr(image, "convert"):
        # PIL.Image — convert to RGB PNG bytes for downstream consumers.
        pil_image = image.convert("RGB")
        buf = io.BytesIO()
        pil_image.save(buf, format="PNG")
        image_bytes = buf.getvalue()
        width, height = pil_image.size
    elif isinstance(image, dict) and "bytes" in image:
        image_bytes = image["bytes"]
        from PIL import Image as PILImage

        with PILImage.open(io.BytesIO(image_bytes)) as pil_image:
            width, height = pil_image.size
    else:
        return None

    instruction = sample.get("instruction") or sample.get("task") or ""
    if not instruction:
        return None

    bbox_raw = (
        sample.get("bbox")
        or (sample.get("action_detection") or {}).get("bbox")
    )
    if bbox_raw is None:
        return None
    bbox_norm = _bbox_to_normalised(list(bbox_raw), width, height)

    task_id = (
        sample.get("id")
        or sample.get("task_id")
        or f"screenspot-pro-{index:05d}"
    )

    metadata = {
        "platform": str(sample.get("platform") or "<unknown>"),
        "application": str(sample.get("application") or "<unknown>"),
        "group": str(sample.get("group") or "<unknown>"),
        "instruction_style": str(sample.get("instruction_style") or "<unknown>"),
    }

    return GroundingTask(
        task_id=str(task_id),
        image_bytes=image_bytes,
        image_size=(width, height),
        instruction=str(instruction),
        ground_truth_bbox=bbox_norm,
        metadata=metadata,
    )


def _iter_samples() -> Iterator[dict[str, Any]]:
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise SystemExit(
            "benchmarks/requirements.txt must be installed (datasets). "
            "Run: pip install -r benchmarks/requirements.txt"
        ) from exc

    # ScreenSpot-Pro typically lives in a single `test` split.
    ds = load_dataset(HF_REPO)
    split = "test" if "test" in ds else next(iter(ds))
    yield from ds[split]


def load_tasks(tier: str) -> list[GroundingTask]:
    all_tasks: list[GroundingTask] = []
    for i, sample in enumerate(_iter_samples()):
        task = _to_task(sample, i)
        if task is not None:
            all_tasks.append(task)

    if tier == "subset":
        return load_or_create_subset(
            name=DATASET_NAME,
            all_tasks=all_tasks,
            n=SUBSET_N,
            strata_keys=STRATA,
        )
    if tier == "full":
        return all_tasks
    raise ValueError(f"unknown tier: {tier!r}")
