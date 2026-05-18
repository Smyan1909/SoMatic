"""Benchmark runner CLI.

Examples:
  python -m benchmarks.run --dataset screenspot-pro --arm marks --tier subset
  python -m benchmarks.run --dataset all --arm all --tier full --budget 300
  python -m benchmarks.run --dataset venusbench-gd --arm raw --tier subset --dry-run

Run `python -m benchmarks.run --help` for the full list of options.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from pathlib import Path

from .common.agents import build_agent
from .common.openai_client import OpenAIVisionClient
from .common.runner import RunConfig, run_eval
from .common.somatic_client import InProcessSomaticClient

DATASETS = ("screenspot-pro", "venusbench-gd")
ARMS = ("marks", "coords", "raw")
TIERS = ("subset", "full")

RESULTS_DIR = Path(__file__).resolve().parent / "results" / "raw"


def _load_tasks(dataset: str, tier: str):
    if dataset == "screenspot-pro":
        from .datasets import screenspot_pro

        return screenspot_pro.load_tasks(tier)
    if dataset == "venusbench-gd":
        from .datasets import venusbench_gd

        return venusbench_gd.load_tasks(tier)
    raise ValueError(f"unknown dataset: {dataset!r}")


def _write_manifest(*, dataset: str, arm: str, tier: str, openai, output_path: Path) -> None:
    manifest_path = output_path.with_suffix(".manifest.json")
    manifest = {
        "dataset": dataset,
        "arm": arm,
        "tier": tier,
        "model": openai.model,
        "pricing": {
            "input_per_mtok_usd": openai.pricing.input_per_mtok,
            "output_per_mtok_usd": openai.pricing.output_per_mtok,
        },
        "started_at": _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "results_path": str(output_path),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def _run_one(args, dataset: str, arm: str) -> int:
    print(f"\n=== {dataset} / {arm} / {args.tier} ===", flush=True)
    tasks = _load_tasks(dataset, args.tier)
    if args.dry_run:
        tasks = tasks[:1]
    elif args.max_tasks is not None:
        tasks = tasks[: args.max_tasks]
    if not tasks:
        print("  (no tasks; skipping)", flush=True)
        return 0
    print(f"  loaded {len(tasks)} tasks", flush=True)

    openai = OpenAIVisionClient()
    openai.probe()

    somatic = InProcessSomaticClient() if arm != "raw" else None
    agent = build_agent(arm, openai, somatic)

    timestamp = _dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    output_path = RESULTS_DIR / f"{dataset}__{arm}__{args.tier}__{timestamp}.jsonl"
    config = RunConfig(
        dataset=dataset,
        arm=arm,
        tier=args.tier,
        budget_usd=args.budget,
        max_tasks=args.max_tasks,
        resume_from=args.resume,
    )

    outcome = run_eval(tasks, agent, config, openai, output_path)
    _write_manifest(dataset=dataset, arm=arm, tier=args.tier, openai=openai, output_path=output_path)

    s = outcome.summary
    print(
        f"  done: {s['n']} tasks, Acc@Center={s['acc']:.2%}, "
        f"cost=${s['cost_usd']:.2f}, elapsed={s['elapsed_s']:.1f}s, "
        f"out={output_path}",
        flush=True,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="benchmarks.run", description="SoMatic benchmark runner")
    parser.add_argument("--dataset", choices=DATASETS + ("all",), required=True)
    parser.add_argument("--arm", choices=ARMS + ("all",), required=True)
    parser.add_argument("--tier", choices=TIERS, required=True)
    parser.add_argument("--budget", type=float, default=50.0, help="USD cap; aborts cleanly if exceeded mid-run.")
    parser.add_argument("--dry-run", action="store_true", help="Run exactly 1 task per (dataset, arm) for smoke testing.")
    parser.add_argument("--max-tasks", type=int, default=None)
    parser.add_argument("--resume", type=Path, default=None, help="Path to a prior JSONL whose task ids should be skipped.")
    args = parser.parse_args(argv)

    datasets = DATASETS if args.dataset == "all" else (args.dataset,)
    arms = ARMS if args.arm == "all" else (args.arm,)

    rc = 0
    for ds in datasets:
        for arm in arms:
            try:
                rc |= _run_one(args, ds, arm)
            except SystemExit as exc:
                # Surface SystemExit messages without aborting the whole matrix.
                print(f"  {ds}/{arm} aborted: {exc}", file=sys.stderr)
                rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
