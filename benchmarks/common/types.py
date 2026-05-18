"""Frozen dataclasses for benchmark tasks, predictions, and results.

Mirrors `src/somatic/marks.py`'s `Mark` dataclass approach: small frozen
records, no behaviour, JSON-serialisable through `dataclasses.asdict` (with
bytes fields kept out of the JSON payload — those are runtime-only).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class GroundingTask:
    task_id: str
    image_bytes: bytes
    image_size: tuple[int, int]  # (width, height) in original pixels
    instruction: str
    # Normalised [0,1] xyxy bbox. None for refusal-style tasks where the agent
    # is supposed to refuse rather than emit a coordinate.
    ground_truth_bbox: tuple[float, float, float, float] | None
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Prediction:
    point: tuple[int, int] | None  # pixel coords; None if agent refused / parse failed
    raw_response: str
    input_tokens: int
    output_tokens: int
    elapsed_ms: float
    error: str | None = None


@dataclass(frozen=True)
class Result:
    task_id: str
    arm: str  # "marks" | "coords" | "raw"
    dataset: str  # "screenspot-pro" | "venusbench-gd"
    correct: bool
    prediction: Prediction
    ground_truth_bbox: tuple[float, float, float, float] | None
    image_size: tuple[int, int]
    metadata: Mapping[str, str] = field(default_factory=dict)

    def to_jsonable(self) -> dict[str, Any]:
        """JSON-friendly view: bytes excluded, tuples flattened to lists."""
        return {
            "task_id": self.task_id,
            "arm": self.arm,
            "dataset": self.dataset,
            "correct": self.correct,
            "prediction": {
                "point": list(self.prediction.point) if self.prediction.point else None,
                "raw_response": self.prediction.raw_response,
                "input_tokens": self.prediction.input_tokens,
                "output_tokens": self.prediction.output_tokens,
                "elapsed_ms": self.prediction.elapsed_ms,
                "error": self.prediction.error,
            },
            "ground_truth_bbox": list(self.ground_truth_bbox) if self.ground_truth_bbox else None,
            "image_size": list(self.image_size),
            "metadata": dict(self.metadata),
        }
