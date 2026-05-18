"""The three benchmark agents.

Each agent receives a `GroundingTask` and returns a `Prediction`. The three
arms each ablate a distinct ingredient:

- `raw`    — no SoMatic; pure VLM staring at the raw image.
- `coords` — SoMatic's detected boxes passed as TEXT only (no visual overlay);
             tests whether structural detection alone helps the VLM.
- `marks`  — full SoMatic: annotated image + marks JSON. The delta from
             coords to marks measures the value of the visual annotation
             specifically.
"""
from __future__ import annotations

import base64
import json
import time
from typing import Protocol

from .openai_client import VisionClient
from .prompts import COORDS_PROMPT, COORDS_WITH_HINTS_PROMPT, MARKS_PROMPT
from .somatic_client import InProcessSomaticClient, SomaticResponse
from .types import GroundingTask, Prediction


class Agent(Protocol):
    name: str
    needs_somatic: bool

    def predict(self, task: GroundingTask) -> Prediction: ...


def _format_marks(som: SomaticResponse) -> str:
    return json.dumps(
        [
            {"id": m["id"], "bbox": m["bbox"], "confidence": m["confidence"]}
            for m in som.marks
        ],
        indent=2,
    )


def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {}


def _coerce_point(payload: dict) -> tuple[int, int] | None:
    x = payload.get("x")
    y = payload.get("y")
    if x is None or y is None:
        return None
    try:
        return (int(x), int(y))
    except (TypeError, ValueError):
        return None


def _resolve_marks_action(payload: dict, marks: list[dict]) -> tuple[int, int] | None:
    """Map the GPT response (one of click / click_near / click_xy / refuse)
    to a concrete pixel point. Mirrors SoMatic's CLI: `click <id>`,
    `click_near <id> --dx --dy`, and `click x,y` are first-class actions."""
    action = (payload.get("action") or "").lower()

    if action == "refuse":
        return None

    if action == "click":
        mid = payload.get("mark_id")
        try:
            mid = int(mid) if mid is not None else None
        except (TypeError, ValueError):
            return None
        mark = next((m for m in marks if m["id"] == mid), None)
        if mark is None:
            return None
        cx, cy = mark["center"]
        return (int(cx), int(cy))

    if action == "click_near":
        mid = payload.get("mark_id")
        try:
            mid = int(mid) if mid is not None else None
            dx = int(payload.get("dx", 0) or 0)
            dy = int(payload.get("dy", 0) or 0)
        except (TypeError, ValueError):
            return None
        mark = next((m for m in marks if m["id"] == mid), None)
        if mark is None:
            return None
        cx, cy = mark["center"]
        return (int(cx + dx), int(cy + dy))

    if action == "click_xy":
        x = payload.get("x")
        y = payload.get("y")
        if x is None or y is None:
            return None
        try:
            return (int(x), int(y))
        except (TypeError, ValueError):
            return None

    # Backwards-compat: an older single-action prompt expected {"mark_id": N}.
    # Honour that shape too in case the model emits it.
    if "mark_id" in payload:
        try:
            mid = int(payload["mark_id"]) if payload["mark_id"] is not None else None
        except (TypeError, ValueError):
            return None
        if mid is None:
            return None
        mark = next((m for m in marks if m["id"] == mid), None)
        if mark is None:
            return None
        cx, cy = mark["center"]
        return (int(cx), int(cy))

    return None


class SoMaticMarksAgent:
    """Full SoMatic SKILL: the agent sees the annotated image + marks list and
    can respond with one of three actions, matching the SKILL.md operating
    loop: `click <id>`, `click_near <id> --dx --dy`, or `click x,y`."""

    name = "marks"
    needs_somatic = True

    def __init__(self, openai: VisionClient, somatic: InProcessSomaticClient) -> None:
        self.openai = openai
        self.somatic = somatic

    def predict(self, task: GroundingTask) -> Prediction:
        t0 = time.perf_counter()
        som = self.somatic.infer(task.image_bytes)
        marks_text = _format_marks(som)
        width, height = task.image_size
        prompt = MARKS_PROMPT.format(
            instruction=task.instruction,
            marks=marks_text,
            width=width,
            height=height,
        )
        resp = self.openai.ask(image_b64=som.annotated_image_b64, prompt=prompt)
        payload = _parse_json(resp.text)
        point = _resolve_marks_action(payload, som.marks)
        return Prediction(
            point=point,
            raw_response=resp.text,
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            elapsed_ms=(time.perf_counter() - t0) * 1000.0,
        )


class SoMaticCoordsAgent:
    """SoMatic detects elements but does NOT visually annotate the image.
    The raw image + the detected element list (as text) are sent to GPT;
    the model is asked for an (x, y) coordinate. Isolates the contribution
    of the visual annotation overlay vs. structural hints alone."""

    name = "coords"
    needs_somatic = True

    def __init__(self, openai: VisionClient, somatic: InProcessSomaticClient) -> None:
        self.openai = openai
        self.somatic = somatic

    def predict(self, task: GroundingTask) -> Prediction:
        t0 = time.perf_counter()
        som = self.somatic.infer(task.image_bytes)
        marks_text = _format_marks(som)
        prompt = COORDS_WITH_HINTS_PROMPT.format(
            instruction=task.instruction,
            marks=marks_text,
        )
        # Send the RAW image — the visual annotation overlay is the ingredient
        # we're holding out here.
        raw_b64 = base64.b64encode(task.image_bytes).decode("ascii")
        resp = self.openai.ask(image_b64=raw_b64, prompt=prompt)
        payload = _parse_json(resp.text)
        return Prediction(
            point=_coerce_point(payload),
            raw_response=resp.text,
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            elapsed_ms=(time.perf_counter() - t0) * 1000.0,
        )


class RawGPTAgent:
    """No SoMatic at all. Raw image + plain instruction → (x, y)."""

    name = "raw"
    needs_somatic = False

    def __init__(self, openai: VisionClient) -> None:
        self.openai = openai

    def predict(self, task: GroundingTask) -> Prediction:
        t0 = time.perf_counter()
        prompt = COORDS_PROMPT.format(instruction=task.instruction)
        raw_b64 = base64.b64encode(task.image_bytes).decode("ascii")
        resp = self.openai.ask(image_b64=raw_b64, prompt=prompt)
        payload = _parse_json(resp.text)
        return Prediction(
            point=_coerce_point(payload),
            raw_response=resp.text,
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            elapsed_ms=(time.perf_counter() - t0) * 1000.0,
        )


def build_agent(
    arm: str,
    openai: VisionClient,
    somatic: InProcessSomaticClient | None = None,
) -> Agent:
    if arm == "marks":
        assert somatic is not None, "marks arm requires a SoMatic client"
        return SoMaticMarksAgent(openai, somatic)
    if arm == "coords":
        assert somatic is not None, "coords arm requires a SoMatic client"
        return SoMaticCoordsAgent(openai, somatic)
    if arm == "raw":
        return RawGPTAgent(openai)
    raise ValueError(f"unknown arm: {arm!r}")
