"""Aggregator: walk results/raw/, build RESULTS.md and figures."""
from __future__ import annotations

import argparse
import datetime as _dt
import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RESULTS_DIR = Path(__file__).resolve().parent / "results"
RAW_DIR = RESULTS_DIR / "raw"
FIGURES_DIR = RESULTS_DIR / "figures"
RESULTS_MD = RESULTS_DIR / "RESULTS.md"

REFERENCE_NUMBERS = {
    "screenspot-pro": "OmniParser + GPT-4o = 39.6% (paper); verify on the live leaderboard before publishing.",
    "venusbench-gd": "Dataset released Dec 2025; published baselines pending — see arXiv 2512.16501.",
}


@dataclass
class RunEntry:
    dataset: str
    arm: str
    tier: str
    timestamp: str
    path: Path
    manifest: dict[str, Any]
    records: list[dict[str, Any]]


def _parse_filename(path: Path) -> tuple[str, str, str, str] | None:
    stem = path.stem
    parts = stem.split("__")
    if len(parts) != 4:
        return None
    dataset, arm, tier, timestamp = parts
    return dataset, arm, tier, timestamp


def _load_runs() -> list[RunEntry]:
    if not RAW_DIR.exists():
        return []
    entries: list[RunEntry] = []
    for path in sorted(RAW_DIR.glob("*.jsonl")):
        parsed = _parse_filename(path)
        if parsed is None:
            continue
        dataset, arm, tier, timestamp = parsed
        manifest_path = path.with_suffix(".manifest.json")
        manifest = (
            json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest_path.exists()
            else {}
        )
        records: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        entries.append(RunEntry(dataset, arm, tier, timestamp, path, manifest, records))
    return entries


def _latest_per_combo(entries: Iterable[RunEntry]) -> dict[tuple[str, str, str], RunEntry]:
    by_combo: dict[tuple[str, str, str], RunEntry] = {}
    for entry in entries:
        key = (entry.dataset, entry.arm, entry.tier)
        prior = by_combo.get(key)
        if prior is None or entry.timestamp > prior.timestamp:
            by_combo[key] = entry
    return by_combo


def _acc(records: Iterable[dict[str, Any]]) -> tuple[int, int, float]:
    total = 0
    correct = 0
    for r in records:
        total += 1
        if r.get("correct"):
            correct += 1
    return total, correct, (correct / total) if total else 0.0


def _venusbench_headline_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Exclude refusal_spatial from the headline VenusBench-GD score."""
    return [
        r for r in records
        if r.get("metadata", {}).get("task_type") != "refusal_spatial"
    ]


def _by_metadata(records: list[dict[str, Any]], key: str) -> dict[str, tuple[int, int, float]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        value = str(r.get("metadata", {}).get(key, "<unknown>"))
        buckets[value].append(r)
    return {k: _acc(v) for k, v in buckets.items()}


def _table(rows: list[list[str]], headers: list[str]) -> str:
    widths = [max(len(headers[i]), *(len(row[i]) for row in rows)) for i in range(len(headers))]
    lines = []
    lines.append("| " + " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers)) + " |")
    lines.append("| " + " | ".join("-" * widths[i] for i in range(len(headers))) + " |")
    for row in rows:
        lines.append("| " + " | ".join(row[i].ljust(widths[i]) for i in range(len(headers))) + " |")
    return "\n".join(lines)


def _pct(value: float, n: int) -> str:
    if n == 0:
        return "—"
    return f"{value * 100:.1f}%"


def _maybe_make_figures(entries_by_combo: dict[tuple[str, str, str], RunEntry]) -> list[Path]:
    """Generate per-dataset bar chart. Returns the list of figure paths. If
    matplotlib isn't installed, returns []."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return []
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for dataset in sorted({k[0] for k in entries_by_combo}):
        arms_present = [a for a in ("marks", "coords", "raw") if any(k[0] == dataset and k[1] == a for k in entries_by_combo)]
        if not arms_present:
            continue
        values: list[float] = []
        for arm in arms_present:
            for tier in ("full", "subset"):
                entry = entries_by_combo.get((dataset, arm, tier))
                if entry is None:
                    continue
                recs = entry.records
                if dataset == "venusbench-gd":
                    recs = _venusbench_headline_records(recs)
                _, _, acc = _acc(recs)
                values.append(acc * 100)
                break
            else:
                values.append(0.0)
        fig, ax = plt.subplots(figsize=(6, 3.5))
        ax.bar(arms_present, values, color=["#7d5ba6", "#5b8def", "#8fb0a6"][: len(arms_present)])
        ax.set_ylabel("Acc@Center (%)")
        ax.set_title(f"{dataset} — Acc@Center by arm")
        ax.set_ylim(0, 100)
        for i, v in enumerate(values):
            ax.text(i, v + 1, f"{v:.1f}%", ha="center", va="bottom", fontsize=9)
        fig.tight_layout()
        out = FIGURES_DIR / f"{dataset}.png"
        fig.savefig(out, dpi=160)
        plt.close(fig)
        paths.append(out)
    return paths


def render(entries: list[RunEntry]) -> str:
    by_combo = _latest_per_combo(entries)
    if not by_combo:
        return (
            "# SoMatic Benchmark Results\n\n"
            "No benchmark runs yet. Run `python -m benchmarks.run --dataset all --arm all --tier subset` to populate this page.\n"
        )

    timestamp = _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    models = sorted({e.manifest.get("model", "?") for e in by_combo.values()})
    model_str = ", ".join(models)
    tier_str = sorted({e.tier for e in by_combo.values()})

    lines: list[str] = []
    lines.append("# SoMatic Benchmark Results")
    lines.append("")
    lines.append(f"_Last updated: {timestamp} • Models: {model_str} • Tiers: {', '.join(tier_str)}_")
    lines.append("")
    lines.append("## Headline")
    lines.append("")

    headline_rows = []
    for dataset in ("screenspot-pro", "venusbench-gd"):
        row = [dataset]
        n_total = 0
        for arm in ("marks", "coords", "raw"):
            tier_pref = ("full", "subset")
            entry = next(
                (by_combo.get((dataset, arm, t)) for t in tier_pref if by_combo.get((dataset, arm, t))),
                None,
            )
            if entry is None:
                row.append("—")
                continue
            recs = entry.records
            if dataset == "venusbench-gd":
                recs = _venusbench_headline_records(recs)
            n, _, acc = _acc(recs)
            n_total = max(n_total, n)
            row.append(_pct(acc, n))
        row[0] = f"{dataset} (n={n_total})"
        row.append(REFERENCE_NUMBERS.get(dataset, "—"))
        headline_rows.append(row)
    lines.append(
        _table(
            headline_rows,
            headers=["Dataset", "SoMatic+marks+GPT", "SoMatic+coords+GPT", "Raw GPT", "Reference"],
        )
    )

    # Per-platform / per-group breakdowns for ScreenSpot-Pro.
    for breakdown_key, breakdown_title in (
        ("platform", "ScreenSpot-Pro per-platform"),
        ("group", "ScreenSpot-Pro per-group"),
    ):
        lines.append("")
        lines.append(f"## {breakdown_title}")
        lines.append("")
        rows: dict[str, list[str]] = {}
        for arm in ("marks", "coords", "raw"):
            entry = next(
                (by_combo.get(("screenspot-pro", arm, t)) for t in ("full", "subset") if by_combo.get(("screenspot-pro", arm, t))),
                None,
            )
            if entry is None:
                continue
            for value, (n, _c, acc) in sorted(_by_metadata(entry.records, breakdown_key).items()):
                rows.setdefault(value, [value, "—", "—", "—"])
                pos = {"marks": 1, "coords": 2, "raw": 3}[arm]
                rows[value][pos] = _pct(acc, n)
        if rows:
            lines.append(_table(list(rows.values()), headers=[breakdown_key.capitalize(), "marks", "coords", "raw"]))
        else:
            lines.append("_No ScreenSpot-Pro runs yet._")

    # VenusBench-GD per-task-type breakdown.
    lines.append("")
    lines.append("## VenusBench-GD per-task-type")
    lines.append("")
    rows = {}
    for arm in ("marks", "coords", "raw"):
        entry = next(
            (by_combo.get(("venusbench-gd", arm, t)) for t in ("full", "subset") if by_combo.get(("venusbench-gd", arm, t))),
            None,
        )
        if entry is None:
            continue
        for value, (n, _c, acc) in sorted(_by_metadata(entry.records, "task_type").items()):
            rows.setdefault(value, [value, "—", "—", "—"])
            pos = {"marks": 1, "coords": 2, "raw": 3}[arm]
            rows[value][pos] = _pct(acc, n)
    if rows:
        lines.append(_table(list(rows.values()), headers=["Task type", "marks", "coords", "raw"]))
    else:
        lines.append("_No VenusBench-GD runs yet._")

    # Cost & latency.
    lines.append("")
    lines.append("## Latency & cost (across all runs)")
    lines.append("")
    cost_rows = []
    for arm in ("marks", "coords", "raw"):
        per_arm_records: list[dict[str, Any]] = []
        per_arm_cost = 0.0
        for (ds, a, t), entry in by_combo.items():
            if a != arm:
                continue
            per_arm_records.extend(entry.records)
        if not per_arm_records:
            continue
        mean_ms = sum(r.get("prediction", {}).get("elapsed_ms", 0.0) for r in per_arm_records) / len(per_arm_records)
        in_tok = sum(r.get("prediction", {}).get("input_tokens", 0) for r in per_arm_records)
        out_tok = sum(r.get("prediction", {}).get("output_tokens", 0) for r in per_arm_records)
        # Pricing snapshot from any manifest with this arm.
        pricing_in = pricing_out = 0.0
        for (ds, a, t), entry in by_combo.items():
            if a != arm:
                continue
            p = entry.manifest.get("pricing") or {}
            pricing_in = p.get("input_per_mtok_usd", 5.0)
            pricing_out = p.get("output_per_mtok_usd", 30.0)
            break
        cost = in_tok * pricing_in / 1_000_000 + out_tok * pricing_out / 1_000_000
        cost_rows.append([arm, f"{mean_ms:.0f}", f"${cost:.2f}", f"{in_tok:,} in / {out_tok:,} out"])
    if cost_rows:
        lines.append(_table(cost_rows, headers=["Arm", "Mean ms/task", "Total cost USD", "Tokens"]))

    # Methodology.
    lines.append("")
    lines.append("## Methodology")
    lines.append("")
    lines.append("- **Acc@Center** metric: predicted click point is correct iff it falls inside the ground-truth bbox.")
    lines.append("- **Refusal-spatial** (VenusBench-GD): correct iff the agent emitted no coordinate. Reported as a separate sub-score; **excluded** from the headline VenusBench-GD average to keep the raw-GPT arm's score from being asymmetrically dragged down (raw GPT-5.5 told to return {x,y} will rarely refuse).")
    lines.append("- **Stratified subset** of 200/dataset for the dev tier; full datasets for the final tier. Subsets are pinned in `benchmarks/subsets/*-v1.json` for reproducibility.")
    lines.append("- **GPT image detail**: `original` (preserves dense-UI fidelity).")
    lines.append("- **Temperature**: 0.0; responses parsed as `response_format=json_object`.")
    lines.append("- Source code: [`benchmarks/`](.). One run per (dataset, arm, tier); the aggregator picks the latest timestamp per combo.")
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="benchmarks.aggregate")
    parser.add_argument("--output", type=Path, default=RESULTS_MD)
    args = parser.parse_args(argv)

    entries = _load_runs()
    md = render(entries)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(md, encoding="utf-8")
    paths = _maybe_make_figures(_latest_per_combo(entries))
    print(f"Wrote {args.output} ({len(md)} bytes)")
    if paths:
        print(f"Figures: {[str(p) for p in paths]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
