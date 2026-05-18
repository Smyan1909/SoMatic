"""ScreenSpot-Pro loader.

HF dataset: `likaixin/ScreenSpot-Pro` (MIT). The repo is NOT a standard
`datasets`-library layout; it's raw research data:

    annotations/<app>_<platform>.json    # one JSON list per application
    images/<subdir>/<filename>.png       # screenshots

Each annotation entry has:
    {
      "img_filename": "excel_mac/screenshot_...png",   # path under images/
      "bbox": [x1, y1, x2, y2],                        # absolute pixels
      "instruction": "...",
      "id": "excel_macos_0",
      "application": "excel",
      "platform": "macos",
      "img_size": [width, height],
      "ui_type": "...",
      "group": "Office"
    }

We download annotations eagerly (small) and images lazily (one per task on
demand) so `--dry-run` and `--tier subset` don't pull the full ~4 GB.
"""
from __future__ import annotations

import io
import json
import os
from dataclasses import dataclass, field
from typing import Any, Mapping

from ..common.sampling import load_or_create_subset
from ..common.types import GroundingTask

DATASET_NAME = "screenspot-pro"
HF_REPO = os.environ.get("SOMATIC_BENCH_SCREENSPOT_PRO_REPO", "likaixin/ScreenSpot-Pro")
SUBSET_N = 200
STRATA = ("platform", "group")


@dataclass
class _TaskSource:
    """Lightweight task descriptor for stratified picking. Materialises into a
    full GroundingTask (with image bytes) on demand."""

    task_id: str
    metadata: Mapping[str, str]
    annotation: dict[str, Any]
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

        size = ann.get("img_size")
        if isinstance(size, (list, tuple)) and len(size) == 2:
            width, height = int(size[0]), int(size[1])
        else:
            with PILImage.open(io.BytesIO(image_bytes)) as img:
                width, height = img.size

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


def _list_annotation_files(repo_id: str) -> list[str]:
    from huggingface_hub import HfApi

    api = HfApi()
    files = api.list_repo_files(repo_id=repo_id, repo_type="dataset")
    return [f for f in files if f.startswith("annotations/") and f.endswith(".json")]


def _iter_task_sources(repo_id: str = HF_REPO):
    from huggingface_hub import hf_hub_download

    for ann_path in _list_annotation_files(repo_id):
        local_ann = hf_hub_download(
            repo_id=repo_id,
            filename=ann_path,
            repo_type="dataset",
        )
        with open(local_ann, "r", encoding="utf-8") as f:
            entries = json.load(f)
        if not isinstance(entries, list):
            continue
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            task_id = str(entry.get("id") or f"{ann_path}::{i}")
            metadata = {
                "platform": str(entry.get("platform") or "<unknown>"),
                "application": str(entry.get("application") or "<unknown>"),
                "group": str(entry.get("group") or "<unknown>"),
                "ui_type": str(entry.get("ui_type") or "<unknown>"),
            }
            yield _TaskSource(
                task_id=task_id,
                metadata=metadata,
                annotation=entry,
                repo_id=repo_id,
            )


def load_tasks(tier: str) -> list[GroundingTask]:
    sources = list(_iter_task_sources())
    if not sources:
        return []

    if tier == "subset":
        picked = load_or_create_subset(
            name=DATASET_NAME,
            all_tasks=sources,  # duck-typed: stratified_subset only reads .task_id / .metadata
            n=SUBSET_N,
            strata_keys=STRATA,
        )
    elif tier == "full":
        picked = sources
    else:
        raise ValueError(f"unknown tier: {tier!r}")

    tasks: list[GroundingTask] = []
    for src in picked:
        # mypy: _TaskSource and GroundingTask share only the duck-typed surface used by the picker.
        materialized = src.materialize() if isinstance(src, _TaskSource) else None
        if materialized is not None:
            tasks.append(materialized)
    return tasks
