"""Metric implementations for GUI grounding benchmarks.

Acc@Center is the canonical metric for ScreenSpot-Pro and VenusBench-GD: the
predicted click point is "correct" iff it falls inside the ground-truth bbox.
For refusal-style tasks (VenusBench-GD's `refusal_spatial`), "correct" means
the agent emitted no coordinate.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Mapping

from .types import Result


def acc_at_center(
    point: tuple[int, int] | None,
    bbox: tuple[float, float, float, float] | None,
    image_size: tuple[int, int],
) -> bool:
    """True iff (point falls inside bbox) OR (bbox is None and point is None).

    `bbox` is normalised [0,1] xyxy. `image_size` is (width, height) used to
    project the normalised box back to pixels. `point` is in absolute pixel
    coords.
    """
    if bbox is None:
        # Refusal task: correct iff the agent refused.
        return point is None
    if point is None:
        return False
    width, height = image_size
    x_min, y_min, x_max, y_max = bbox
    px, py = point
    return (
        x_min * width <= px <= x_max * width
        and y_min * height <= py <= y_max * height
    )


def aggregate_by(results: Iterable[Result], key: str) -> dict[str, dict[str, float]]:
    """Group results by a metadata key and compute per-group Acc@Center.

    Returns: { group_value: { "n": <int>, "correct": <int>, "acc": <float> } }.
    `key="__overall__"` collapses everything into a single group.
    """
    buckets: dict[str, list[Result]] = {}
    for r in results:
        if key == "__overall__":
            group_value = "overall"
        else:
            group_value = r.metadata.get(key, "<unknown>")
        buckets.setdefault(group_value, []).append(r)

    return {
        group: {
            "n": len(items),
            "correct": sum(1 for it in items if it.correct),
            "acc": sum(1 for it in items if it.correct) / len(items) if items else 0.0,
        }
        for group, items in buckets.items()
    }


def summary(results: Iterable[Result]) -> Mapping[str, float]:
    """Headline summary: total tasks, correct, accuracy, cost-relevant token sums."""
    items = list(results)
    if not items:
        return {"n": 0, "correct": 0, "acc": 0.0, "input_tokens": 0, "output_tokens": 0}
    correct = sum(1 for it in items if it.correct)
    in_tokens = sum(it.prediction.input_tokens for it in items)
    out_tokens = sum(it.prediction.output_tokens for it in items)
    return {
        "n": len(items),
        "correct": correct,
        "acc": correct / len(items),
        "input_tokens": in_tokens,
        "output_tokens": out_tokens,
    }
