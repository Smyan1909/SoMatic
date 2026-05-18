"""Main eval loop.

Streams `Result` objects as JSONL so a crash doesn't lose work; enforces
budget and max-task caps; supports `--resume <jsonl>` so partial runs can
continue without paying for completed tasks twice.
"""
from __future__ import annotations

import json
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .agents import Agent
from .metrics import acc_at_center
from .openai_client import VisionClient
from .types import GroundingTask, Result


@dataclass
class RunConfig:
    dataset: str
    arm: str
    tier: str
    budget_usd: float = 50.0
    max_tasks: int | None = None
    resume_from: Path | None = None
    progress_interval: int = 20


@dataclass
class RunOutcome:
    output_path: Path
    summary: dict


def _load_completed_ids(resume_path: Path) -> set[str]:
    if not resume_path.exists():
        return set()
    seen: set[str] = set()
    with resume_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            tid = rec.get("task_id")
            if tid:
                seen.add(tid)
    return seen


def run_eval(
    tasks: Iterable[GroundingTask],
    agent: Agent,
    config: RunConfig,
    openai: VisionClient,
    output_path: Path,
    *,
    on_result: Callable[[Result], None] | None = None,
) -> RunOutcome:
    """Run one (dataset, arm) eval loop, streaming results to `output_path`.

    Aborts cleanly if the running cost estimate exceeds `config.budget_usd`
    or `config.max_tasks` is reached. If `config.resume_from` is set, tasks
    whose `task_id` is already in that JSONL are skipped.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    completed = _load_completed_ids(config.resume_from) if config.resume_from else set()

    correct = 0
    seen = 0
    started = time.perf_counter()

    # Open in append mode if we're resuming into the same file; otherwise truncate.
    mode = "a" if config.resume_from and config.resume_from.resolve() == output_path.resolve() else "w"
    with output_path.open(mode, encoding="utf-8") as f:
        for task in tasks:
            if config.max_tasks is not None and seen >= config.max_tasks:
                break
            if task.task_id in completed:
                continue

            try:
                prediction = agent.predict(task)
            except Exception as exc:  # noqa: BLE001 — record and continue
                prediction_err = type(exc).__name__ + ": " + str(exc)
                # Construct a failed Prediction so the JSONL line is well-formed.
                from .types import Prediction

                prediction = Prediction(
                    point=None,
                    raw_response="",
                    input_tokens=0,
                    output_tokens=0,
                    elapsed_ms=0.0,
                    error=prediction_err,
                )

            is_correct = acc_at_center(
                prediction.point, task.ground_truth_bbox, task.image_size
            )
            result = Result(
                task_id=task.task_id,
                arm=config.arm,
                dataset=config.dataset,
                correct=is_correct,
                prediction=prediction,
                ground_truth_bbox=task.ground_truth_bbox,
                image_size=task.image_size,
                metadata=task.metadata,
            )
            f.write(json.dumps(result.to_jsonable()) + "\n")
            f.flush()

            if on_result is not None:
                on_result(result)

            seen += 1
            correct += int(is_correct)

            if seen % config.progress_interval == 0:
                elapsed = time.perf_counter() - started
                cost = openai.cost_estimate_usd()
                print(
                    f"  [{config.arm:<6} {config.dataset:<14}] {seen} tasks  "
                    f"Acc@Center={correct/seen:.2%}  cost=${cost:.2f}  "
                    f"elapsed={elapsed:.1f}s",
                    flush=True,
                )

            current_cost = openai.cost_estimate_usd()
            if current_cost > config.budget_usd:
                print(
                    f"  BUDGET_EXCEEDED at {seen} tasks (${current_cost:.2f} > "
                    f"${config.budget_usd:.2f}); aborting cleanly.",
                    file=sys.stderr,
                )
                break

    summary = {
        "n": seen,
        "correct": correct,
        "acc": (correct / seen) if seen else 0.0,
        "cost_usd": openai.cost_estimate_usd(),
        "elapsed_s": time.perf_counter() - started,
        "input_tokens": openai.total_input_tokens,
        "output_tokens": openai.total_output_tokens,
        "model": openai.model,
    }
    return RunOutcome(output_path=output_path, summary=summary)
