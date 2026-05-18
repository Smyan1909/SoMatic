"""VenusBench-GD loader.

HF dataset: `inclusionAI/VenusBench-GD` (MIT). Like ScreenSpot-Pro, this is
NOT a standard `datasets`-library layout. The repo holds:

    instruction/<task_type>.json     # one JSON list per task type
    images/<platform>/<app>/<file>   # screenshots organised by platform/app

Each instruction entry has:
    {
      "img_filename": "mobile/excel/...png",   # path under images/
      "instruction": "...",
      "category": "element_grounding",
      "bbox": [x1, y1, x2, y2],                # absolute pixels; null for refusal
      "label": "text input",
      "data_type": "bbox"
    }

Refusal-grounding entries are the impossible-instruction subset; the agent
is expected to refuse rather than emit a coordinate. We set
`ground_truth_bbox=None` for those; the metric in `common/metrics.py`
treats "agent emitted no coordinate" as correct.

We download instruction JSONs eagerly (small) and images lazily on demand.
"""
from __future__ import annotations

import io
import json
import os
from dataclasses import dataclass, field
from typing import Any, Mapping

from ..common.sampling import load_or_create_subset
from ..common.types import GroundingTask

DATASET_NAME = "venusbench-gd"
HF_REPO = os.environ.get("SOMATIC_BENCH_VENUSBENCH_GD_REPO", "inclusionAI/VenusBench-GD")
SUBSET_N = 200
STRATA = ("task_type", "platform")
# Actual filenames in the HF repo's instruction/ directory:
TASK_FILES = (
    "element_grounding.json",
    "functional_grounding.json",
    "reason_grounding.json",
    "refusal_grounding.json",
    "spatial_grounding.json",
    "visual_grounding.json",
)
REFUSAL_TASK_TYPE = "refusal_grounding"


@dataclass
class _TaskSource:
    task_id: str
    metadata: Mapping[str, str]
    annotation: dict[str, Any]
    is_refusal: bool
    repo_id: str = field(default=HF_REPO)

    def materialize(self) -> GroundingTask | None:
        from huggingface_hub import hf_hub_download
        from PIL import Image as PILImage

        ann = self.annotation
        img_filename = ann.get("img_filename")
        if not img_filename:
            return None
        try:
            local_image = hf_hub_download(
                repo_id=self.repo_id,
                filename=f"images/{img_filename}",
                repo_type="dataset",
            )
        except Exception:
            return None
        with open(local_image, "rb") as f:
            image_bytes = f.read()
        with PILImage.open(io.BytesIO(image_bytes)) as img:
            width, height = img.size

        if self.is_refusal:
            bbox_norm = None
        else:
            bbox = ann.get("bbox")
            if not (isinstance(bbox, (list, tuple)) and len(bbox) == 4):
                return None
            x1, y1, x2, y2 = bbox
            bbox_norm = (
                max(0.0, x1 / width),
                max(0.0, y1 / height),
                min(1.0, x2 / width),
                min(1.0, y2 / height),
            )

        return GroundingTask(
            task_id=self.task_id,
            image_bytes=image_bytes,
            image_size=(width, height),
            instruction=str(ann.get("instruction") or ""),
            ground_truth_bbox=bbox_norm,
            metadata=dict(self.metadata),
        )


def _platform_from_filename(img_filename: str) -> str:
    # img_filename starts with platform: "mobile/...", "web/...", "desktop/..."
    if not img_filename:
        return "<unknown>"
    head = img_filename.split("/", 1)[0]
    return head if head else "<unknown>"


def _iter_task_sources(repo_id: str = HF_REPO):
    from huggingface_hub import hf_hub_download

    for fname in TASK_FILES:
        task_type = fname[: -len(".json")]
        try:
            local_path = hf_hub_download(
                repo_id=repo_id,
                filename=f"instruction/{fname}",
                repo_type="dataset",
            )
        except Exception:
            continue
        with open(local_path, "r", encoding="utf-8") as f:
            try:
                entries = json.load(f)
            except json.JSONDecodeError:
                continue
        if not isinstance(entries, list):
            continue
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            img_filename = str(entry.get("img_filename") or "")
            metadata = {
                "task_type": task_type,
                "platform": _platform_from_filename(img_filename),
                "label": str(entry.get("label") or "<unknown>"),
                "data_type": str(entry.get("data_type") or "<unknown>"),
            }
            task_id = f"venusbench-gd::{task_type}::{i:05d}"
            yield _TaskSource(
                task_id=task_id,
                metadata=metadata,
                annotation=entry,
                is_refusal=(task_type == REFUSAL_TASK_TYPE),
                repo_id=repo_id,
            )


def load_tasks(tier: str) -> list[GroundingTask]:
    sources = list(_iter_task_sources())
    if not sources:
        return []

    if tier == "subset":
        picked = load_or_create_subset(
            name=DATASET_NAME,
            all_tasks=sources,  # duck-typed
            n=SUBSET_N,
            strata_keys=STRATA,
        )
    elif tier == "full":
        picked = sources
    else:
        raise ValueError(f"unknown tier: {tier!r}")

    tasks: list[GroundingTask] = []
    for src in picked:
        materialized = src.materialize() if isinstance(src, _TaskSource) else None
        if materialized is not None:
            tasks.append(materialized)
    return tasks
