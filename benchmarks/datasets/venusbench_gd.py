"""VenusBench-GD loader.

HF dataset: `inclusionAI/VenusBench-GD` (MIT). 6,166 samples across 6 task
types (element_grounding, spatial_grounding, visual_grounding,
reasoning_grounding, functional_grounding, refusal_spatial), three platforms
(web / mobile / desktop), and ~97 applications.

Refusal-spatial samples set `ground_truth_bbox=None` — the agent is expected
to refuse. The metric in `common/metrics.py` treats "predicted any
coordinate" as wrong for those, and the aggregator reports refusal as a
separate sub-score (excluded from the headline VenusBench-GD average).
"""
from __future__ import annotations

import io
import os
from collections.abc import Iterator
from typing import Any

from ..common.sampling import load_or_create_subset
from ..common.types import GroundingTask

DATASET_NAME = "venusbench-gd"
HF_REPO = os.environ.get("SOMATIC_BENCH_VENUSBENCH_GD_REPO", "inclusionAI/VenusBench-GD")
SUBSET_N = 200
STRATA = ("task_type", "platform")
TASK_TYPES = (
    "element_grounding",
    "spatial_grounding",
    "visual_grounding",
    "reasoning_grounding",
    "functional_grounding",
    "refusal_spatial",
)


def _normalise_bbox(
    bbox: list[float] | None, width: int, height: int
) -> tuple[float, float, float, float] | None:
    if bbox is None or len(bbox) != 4:
        return None
    x1, y1, x2, y2 = bbox
    # Detect whether the bbox is already normalised or in absolute pixels.
    if max(bbox) <= 1.5:
        # Already in [0,1] (allow a tiny slack above 1.0 for rounding).
        return (
            max(0.0, min(1.0, x1)),
            max(0.0, min(1.0, y1)),
            max(0.0, min(1.0, x2)),
            max(0.0, min(1.0, y2)),
        )
    return (
        max(0.0, x1 / width),
        max(0.0, y1 / height),
        min(1.0, x2 / width),
        min(1.0, y2 / height),
    )


def _to_task(sample: dict[str, Any], task_type: str, index: int) -> GroundingTask | None:
    image = sample.get("image")
    if image is None:
        return None
    if hasattr(image, "convert"):
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

    instruction = sample.get("instruction") or ""
    if not instruction:
        return None

    is_refusal = task_type == "refusal_spatial"
    bbox_raw = sample.get("bbox")
    if is_refusal:
        bbox_norm = None
    else:
        if bbox_raw is None:
            return None
        bbox_norm = _normalise_bbox(list(bbox_raw), width, height)
        if bbox_norm is None:
            return None

    task_id = (
        sample.get("image_id")
        or sample.get("id")
        or f"venusbench-gd-{task_type}-{index:05d}"
    )

    metadata = {
        "task_type": task_type,
        "platform": str(sample.get("platform") or "<unknown>"),
        "application": str(sample.get("application") or "<unknown>"),
        "ui_element_type": str(sample.get("ui_element_type") or "<unknown>"),
        "domain": str(sample.get("domain") or "<unknown>"),
        "bbox_validity": str(sample.get("bbox_validity") or "<unknown>"),
    }

    return GroundingTask(
        task_id=str(task_id),
        image_bytes=image_bytes,
        image_size=(width, height),
        instruction=str(instruction),
        ground_truth_bbox=bbox_norm,
        metadata=metadata,
    )


def _iter_samples() -> Iterator[tuple[dict[str, Any], str]]:
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise SystemExit(
            "benchmarks/requirements.txt must be installed (datasets). "
            "Run: pip install -r benchmarks/requirements.txt"
        ) from exc

    # VenusBench-GD organises samples by task type; depending on how the HF
    # repo is uploaded these may surface as separate config names (preferred)
    # or as a single split with a `task_type` column. Probe both.
    try:
        ds = load_dataset(HF_REPO)
    except (ValueError, KeyError):
        ds = None

    if ds is not None and any(k in TASK_TYPES for k in ds.keys()):
        for task_type in TASK_TYPES:
            if task_type not in ds:
                continue
            for sample in ds[task_type]:
                yield sample, task_type
        return

    if ds is not None:
        split = "test" if "test" in ds else next(iter(ds))
        for sample in ds[split]:
            tt = sample.get("task_type") or "<unknown>"
            yield sample, str(tt)
        return

    # Fall back to per-config loads.
    for task_type in TASK_TYPES:
        try:
            from datasets import load_dataset

            ds = load_dataset(HF_REPO, name=task_type)
        except Exception:
            continue
        split = "test" if "test" in ds else next(iter(ds))
        for sample in ds[split]:
            yield sample, task_type


def load_tasks(tier: str) -> list[GroundingTask]:
    all_tasks: list[GroundingTask] = []
    for i, (sample, task_type) in enumerate(_iter_samples()):
        task = _to_task(sample, task_type, i)
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
