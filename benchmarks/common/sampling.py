"""Deterministic stratified subset selector.

Used by the `subset` tier. Pinning the subset to a versioned JSON file under
`benchmarks/subsets/` keeps reruns directly comparable: the same task ids
are picked, and the resulting JSONL files diff cleanly across changes to
the harness or prompt.
"""
from __future__ import annotations

import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Sequence

from .types import GroundingTask


SUBSETS_DIR = Path(__file__).resolve().parent.parent / "subsets"


def _strata_key(task: GroundingTask, keys: Sequence[str]) -> tuple[str, ...]:
    return tuple(str(task.metadata.get(k, "<missing>")) for k in keys)


def _stable_seed(task_id: str, salt: int) -> int:
    h = hashlib.sha256(f"{salt}|{task_id}".encode("utf-8")).hexdigest()
    return int(h[:16], 16)


def stratified_subset(
    tasks: Sequence[GroundingTask],
    n: int,
    strata_keys: Sequence[str],
    *,
    seed: int = 42,
) -> list[GroundingTask]:
    """Pick `n` tasks balanced across the cartesian product of metadata
    values in `strata_keys`.

    Deterministic: the same `tasks` order + same `strata_keys` + same `seed`
    always produces the same ID set. Achieves balance by allocating each
    stratum a quota proportional to its share of the full population
    (largest-remainder rounding) and then picking from each stratum using a
    stable per-task hash for the sort.
    """
    if n >= len(tasks):
        return list(tasks)

    buckets: dict[tuple[str, ...], list[GroundingTask]] = defaultdict(list)
    for task in tasks:
        buckets[_strata_key(task, strata_keys)].append(task)

    total = len(tasks)
    # First-pass quotas via floor of proportional share.
    raw_quotas = {k: n * len(v) / total for k, v in buckets.items()}
    quotas = {k: int(q) for k, q in raw_quotas.items()}
    # Distribute the remainder by largest fractional share, ties broken
    # deterministically on the strata key.
    leftover = n - sum(quotas.values())
    fractional = sorted(
        ((k, raw_quotas[k] - quotas[k]) for k in buckets),
        key=lambda kv: (-kv[1], kv[0]),
    )
    for k, _frac in fractional[:leftover]:
        quotas[k] += 1

    picked: list[GroundingTask] = []
    for k, bucket in buckets.items():
        if quotas[k] <= 0:
            continue
        # Stable sort by per-task hash so the chosen items are deterministic.
        ordered = sorted(bucket, key=lambda t: _stable_seed(t.task_id, seed))
        picked.extend(ordered[: quotas[k]])

    # Final order: stable hash on task_id with the same seed.
    picked.sort(key=lambda t: _stable_seed(t.task_id, seed))
    return picked


def load_or_create_subset(
    name: str,
    all_tasks: Sequence[GroundingTask],
    n: int,
    strata_keys: Sequence[str],
    *,
    seed: int = 42,
    subsets_dir: Path | None = None,
) -> list[GroundingTask]:
    """Read pre-frozen subset task IDs from disk if present; otherwise pick a
    fresh stratified subset and write it for next time."""
    subsets_dir = subsets_dir or SUBSETS_DIR
    subsets_dir.mkdir(parents=True, exist_ok=True)
    path = subsets_dir / f"{name}-v1.json"
    if path.exists():
        ordered_ids = json.loads(path.read_text(encoding="utf-8"))
        # Preserve the saved order (which is the original pick order from the
        # first run) — important for tests that round-trip the subset.
        index = {t.task_id: t for t in all_tasks}
        return [index[i] for i in ordered_ids if i in index]

    picked = stratified_subset(all_tasks, n, strata_keys, seed=seed)
    path.write_text(json.dumps([t.task_id for t in picked], indent=2), encoding="utf-8")
    return picked
