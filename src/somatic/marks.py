from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .jsonio import fail
from .paths import session_file


@dataclass(frozen=True)
class Mark:
    id: int
    bbox: tuple[int, int, int, int]
    center: tuple[int, int]
    label: str | None = None
    confidence: float | None = None
    type: str | None = None
    source: str | None = None
    upstream_idx: int | None = None
    interactable: bool = True

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "Mark":
        bbox = tuple(int(v) for v in payload["bbox"])
        center = payload.get("center")
        if center is None:
            center = ((bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2)
        return cls(
            id=int(payload["id"]),
            bbox=(bbox[0], bbox[1], bbox[2], bbox[3]),
            center=(int(center[0]), int(center[1])),
            label=payload.get("label"),
            confidence=payload.get("confidence"),
            type=payload.get("type"),
            source=payload.get("source"),
            upstream_idx=payload.get("upstream_idx"),
            interactable=bool(payload.get("interactable", True)),
        )

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


def save_marks(payload: dict[str, Any], *, session: str = "default", path: Path | None = None) -> Path:
    target = path or session_file(session)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return target


def load_marks(*, session: str = "default", path: Path | None = None) -> dict[str, Any]:
    target = path or session_file(session)
    if not target.exists():
        fail("marks_not_found", "No mark map is available. Run `somatic screenshot --annotate` first.", details={"path": str(target)})
    return json.loads(target.read_text(encoding="utf-8"))


def get_mark(mark_id: int, *, session: str = "default", path: Path | None = None) -> Mark:
    payload = load_marks(session=session, path=path)
    for item in payload.get("marks", []):
        if int(item.get("id")) == mark_id:
            return Mark.from_payload(item)
    fail("mark_not_found", f"Mark id {mark_id} was not found in the current mark map.", details={"mark_id": mark_id})
    raise AssertionError("unreachable")


def normalize_marks(raw_marks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(raw_marks, start=1):
        bbox = item.get("bbox") or item.get("box") or item.get("rectangle")
        if not bbox or len(bbox) != 4:
            continue
        mark = Mark.from_payload({
            "id": item.get("id", index),
            "bbox": bbox,
            "center": item.get("center"),
            "confidence": item.get("confidence") or item.get("score"),
            "source": item.get("source"),
            "interactable": item.get("interactable", True),
        })
        normalized.append(mark.to_payload())
    return normalized
