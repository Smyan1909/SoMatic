"""Unit tests for the benchmark harness using fakes only — no real OpenAI calls."""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Callable

import pytest
from PIL import Image

from benchmarks.common.agents import RawGPTAgent, SoMaticCoordsAgent, SoMaticMarksAgent
from benchmarks.common.metrics import acc_at_center, aggregate_by, summary
from benchmarks.common.openai_client import OpenAIResponse, PricingSnapshot
from benchmarks.common.runner import RunConfig, run_eval
from benchmarks.common.sampling import load_or_create_subset, stratified_subset
from benchmarks.common.somatic_client import SomaticResponse
from benchmarks.common.types import GroundingTask, Prediction, Result


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeVisionClient:
    def __init__(self, responder: Callable[[str, str], str]):
        self.responder = responder
        self.model = "fake-gpt"
        self.pricing = PricingSnapshot(input_per_mtok=1.0, output_per_mtok=2.0)
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.calls: list[tuple[str, str]] = []

    def probe(self) -> None:  # no-op
        return None

    def ask(self, image_b64: str, prompt: str, *, mime: str = "image/png") -> OpenAIResponse:
        self.calls.append((image_b64[:32], prompt))
        text = self.responder(image_b64, prompt)
        in_tok, out_tok = 50, 5
        self.total_input_tokens += in_tok
        self.total_output_tokens += out_tok
        return OpenAIResponse(text=text, input_tokens=in_tok, output_tokens=out_tok)

    def cost_estimate_usd(self) -> float:
        return self.pricing.cost(self.total_input_tokens, self.total_output_tokens)


class FakeSomaticClient:
    """Returns canned marks regardless of input. The bbox and centre are
    chosen so a known point lies inside the bbox for predictable correctness
    assertions."""

    def __init__(self, marks: list[dict] | None = None):
        self.marks = marks or [
            {"id": 1, "bbox": [10, 10, 90, 90], "center": [50, 50], "confidence": 0.9},
            {"id": 2, "bbox": [120, 120, 180, 180], "center": [150, 150], "confidence": 0.8},
        ]

    def infer(self, image_bytes: bytes) -> SomaticResponse:
        import base64

        return SomaticResponse(
            marks=self.marks,
            annotated_image_b64=base64.b64encode(image_bytes + b"-annotated").decode(),
            raw_image_b64=base64.b64encode(image_bytes).decode(),
            inference_ms=1.5,
        )


def _make_image_bytes(width: int, height: int, color=(255, 255, 255)) -> bytes:
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_task(
    task_id: str,
    *,
    width: int = 200,
    height: int = 200,
    bbox: tuple[float, float, float, float] | None = (0.05, 0.05, 0.45, 0.45),
    instruction: str = "click the button",
    metadata: dict | None = None,
) -> GroundingTask:
    return GroundingTask(
        task_id=task_id,
        image_bytes=_make_image_bytes(width, height),
        image_size=(width, height),
        instruction=instruction,
        ground_truth_bbox=bbox,
        metadata=metadata or {"platform": "windows", "group": "Office"},
    )


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def test_acc_at_center_inside_bbox():
    assert acc_at_center((50, 50), (0.0, 0.0, 0.5, 0.5), (100, 100)) is True


def test_acc_at_center_outside_bbox():
    assert acc_at_center((75, 75), (0.0, 0.0, 0.5, 0.5), (100, 100)) is False


def test_acc_at_center_on_bbox_boundary_is_inclusive():
    # x = x_max * width = 50; y = y_max * height = 50; corner counts as inside.
    assert acc_at_center((50, 50), (0.0, 0.0, 0.5, 0.5), (100, 100)) is True


def test_acc_at_center_refusal_correct_when_no_point():
    assert acc_at_center(None, None, (100, 100)) is True


def test_acc_at_center_refusal_incorrect_when_point_emitted():
    assert acc_at_center((50, 50), None, (100, 100)) is False


def test_acc_at_center_no_point_with_bbox_is_incorrect():
    assert acc_at_center(None, (0.1, 0.1, 0.9, 0.9), (100, 100)) is False


def test_aggregate_by_groups_correctly():
    results = [
        _result("a", True, {"platform": "windows"}),
        _result("b", False, {"platform": "windows"}),
        _result("c", True, {"platform": "macos"}),
    ]
    by_platform = aggregate_by(results, "platform")
    assert by_platform["windows"] == {"n": 2, "correct": 1, "acc": 0.5}
    assert by_platform["macos"] == {"n": 1, "correct": 1, "acc": 1.0}


def _result(task_id: str, correct: bool, metadata: dict) -> Result:
    return Result(
        task_id=task_id,
        arm="marks",
        dataset="screenspot-pro",
        correct=correct,
        prediction=Prediction(
            point=(0, 0) if correct else None,
            raw_response="{}",
            input_tokens=10,
            output_tokens=2,
            elapsed_ms=1.0,
        ),
        ground_truth_bbox=(0.0, 0.0, 1.0, 1.0),
        image_size=(100, 100),
        metadata=metadata,
    )


def test_summary_totals_tokens():
    results = [_result("a", True, {}), _result("b", False, {})]
    s = summary(results)
    assert s["n"] == 2
    assert s["correct"] == 1
    assert s["acc"] == 0.5
    assert s["input_tokens"] == 20
    assert s["output_tokens"] == 4


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------


def test_stratified_subset_is_deterministic():
    tasks = [
        _make_task(f"task-{i:03d}", metadata={"platform": p, "group": g})
        for i, (p, g) in enumerate(
            [("windows", "Dev")] * 50 + [("macos", "Dev")] * 30 + [("linux", "Office")] * 20
        )
    ]
    a = stratified_subset(tasks, n=30, strata_keys=("platform", "group"), seed=42)
    b = stratified_subset(tasks, n=30, strata_keys=("platform", "group"), seed=42)
    assert [t.task_id for t in a] == [t.task_id for t in b]
    assert len(a) == 30


def test_stratified_subset_balances_across_strata():
    tasks = [
        _make_task(f"task-{i:03d}", metadata={"platform": p})
        for i, p in enumerate(["windows"] * 70 + ["macos"] * 30)
    ]
    picked = stratified_subset(tasks, n=10, strata_keys=("platform",), seed=42)
    counts = {p: sum(1 for t in picked if t.metadata["platform"] == p) for p in ("windows", "macos")}
    # 7 windows : 3 macos preserves the 70:30 ratio.
    assert counts == {"windows": 7, "macos": 3}


def test_load_or_create_subset_roundtrips(tmp_path):
    tasks = [
        _make_task(f"task-{i:03d}", metadata={"platform": "windows"})
        for i in range(20)
    ]
    first = load_or_create_subset("test-ds", tasks, n=5, strata_keys=("platform",), subsets_dir=tmp_path)
    assert (tmp_path / "test-ds-v1.json").exists()
    second = load_or_create_subset("test-ds", tasks, n=5, strata_keys=("platform",), subsets_dir=tmp_path)
    assert [t.task_id for t in first] == [t.task_id for t in second]


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------


def test_marks_agent_returns_centre_of_chosen_mark():
    fake_openai = FakeVisionClient(lambda img, prompt: json.dumps({"mark_id": 1}))
    fake_somatic = FakeSomaticClient()
    agent = SoMaticMarksAgent(fake_openai, fake_somatic)

    pred = agent.predict(_make_task("t1"))

    assert pred.point == (50, 50)
    assert pred.input_tokens == 50
    assert pred.output_tokens == 5


def test_marks_agent_handles_refusal():
    fake_openai = FakeVisionClient(lambda img, prompt: json.dumps({"mark_id": None}))
    agent = SoMaticMarksAgent(fake_openai, FakeSomaticClient())

    pred = agent.predict(_make_task("t2"))

    assert pred.point is None


def test_marks_agent_invalid_id_returns_none_point():
    fake_openai = FakeVisionClient(lambda img, prompt: json.dumps({"mark_id": 99}))
    agent = SoMaticMarksAgent(fake_openai, FakeSomaticClient())

    pred = agent.predict(_make_task("t3"))

    assert pred.point is None


def test_coords_agent_returns_xy():
    fake_openai = FakeVisionClient(lambda img, prompt: json.dumps({"x": 42, "y": 17}))
    agent = SoMaticCoordsAgent(fake_openai, FakeSomaticClient())

    pred = agent.predict(_make_task("t4"))

    assert pred.point == (42, 17)


def test_raw_agent_returns_xy():
    fake_openai = FakeVisionClient(lambda img, prompt: json.dumps({"x": 7, "y": 8}))
    agent = RawGPTAgent(fake_openai)

    pred = agent.predict(_make_task("t5"))

    assert pred.point == (7, 8)


def test_coords_and_raw_arms_send_different_prompts():
    """Catches a regression where coords and raw would collapse into duplicates."""
    seen_prompts: list[str] = []

    def responder(img_b64: str, prompt: str) -> str:
        seen_prompts.append(prompt)
        return json.dumps({"x": 1, "y": 1})

    openai = FakeVisionClient(responder)
    coords = SoMaticCoordsAgent(openai, FakeSomaticClient())
    raw = RawGPTAgent(openai)
    task = _make_task("t6")
    coords.predict(task)
    raw.predict(task)

    assert len(seen_prompts) == 2
    coords_prompt, raw_prompt = seen_prompts
    # coords includes the marks JSON; raw does not.
    assert "Detected elements" in coords_prompt
    assert "Detected elements" not in raw_prompt


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def test_run_eval_writes_jsonl_per_task(tmp_path):
    fake_openai = FakeVisionClient(lambda img, prompt: json.dumps({"x": 50, "y": 50}))
    agent = RawGPTAgent(fake_openai)
    tasks = [
        _make_task(f"t-{i}", bbox=(0.0, 0.0, 1.0, 1.0))  # everything correct
        for i in range(5)
    ]
    config = RunConfig(dataset="fake", arm="raw", tier="subset", budget_usd=1000.0)
    out = tmp_path / "results.jsonl"
    outcome = run_eval(tasks, agent, config, fake_openai, out)

    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 5
    payloads = [json.loads(l) for l in lines]
    assert all(p["correct"] for p in payloads)
    assert outcome.summary["n"] == 5
    assert outcome.summary["acc"] == 1.0


def test_run_eval_aborts_when_budget_exceeded(tmp_path):
    # Pricing 1.0 / 2.0 per Mtok × (50 in + 5 out) tokens × 100 tasks =
    # 100 × (50e-6 + 10e-6) = 0.006 USD. Set budget low enough to abort
    # after a few tasks.
    fake_openai = FakeVisionClient(lambda img, prompt: json.dumps({"x": 50, "y": 50}))
    agent = RawGPTAgent(fake_openai)
    tasks = [_make_task(f"t-{i}") for i in range(100)]
    config = RunConfig(dataset="fake", arm="raw", tier="subset", budget_usd=0.0005)
    out = tmp_path / "results.jsonl"

    outcome = run_eval(tasks, agent, config, fake_openai, out)

    written = out.read_text(encoding="utf-8").splitlines()
    assert 1 <= len(written) < 100, f"expected partial write, got {len(written)}"
    assert outcome.summary["n"] == len(written)


def test_run_eval_resume_skips_completed_ids(tmp_path):
    fake_openai = FakeVisionClient(lambda img, prompt: json.dumps({"x": 1, "y": 1}))
    agent = RawGPTAgent(fake_openai)
    tasks = [_make_task(f"t-{i}") for i in range(5)]

    # Pre-write a resume file noting t-0 and t-2 done.
    resume_path = tmp_path / "prior.jsonl"
    resume_path.write_text(
        json.dumps({"task_id": "t-0"}) + "\n" + json.dumps({"task_id": "t-2"}) + "\n",
        encoding="utf-8",
    )
    config = RunConfig(
        dataset="fake", arm="raw", tier="subset", budget_usd=1000.0, resume_from=resume_path
    )
    out = tmp_path / "results.jsonl"
    outcome = run_eval(tasks, agent, config, fake_openai, out)

    written = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    ids = {r["task_id"] for r in written}
    assert ids == {"t-1", "t-3", "t-4"}
    assert outcome.summary["n"] == 3
