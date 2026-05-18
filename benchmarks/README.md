# SoMatic Benchmark Harness

Evaluate SoMatic's Set-of-Marks pipeline + GPT-5.5 on **ScreenSpot-Pro** and **VenusBench-GD**, alongside two controlled baselines: raw GPT-5.5 (no SoMatic) and SoMatic-as-hints (raw image + detected bboxes as text, no visual overlay). Headline metric is **Acc@Center** — predicted click point inside the ground-truth bounding box.

This package is **dev-time tooling only**. It is excluded from the npm tarball, the PyPI sdist, and the wheel.

## Setup

```sh
pip install -e ".[vision]"                          # SoMatic itself
pip install -r benchmarks/requirements.txt          # benchmark-only deps
export OPENAI_API_KEY=sk-...
export SOMATIC_YOLO_ONNX_REPO=<hf-repo-id>          # or SOMATIC_YOLO_ONNX_PATH=/path/to/icon-detect.onnx
```

## Quick start

```sh
# 1-task smoke against the real OpenAI API (sanity check):
python -m benchmarks.run --dataset screenspot-pro --arm raw --tier subset --dry-run

# Full subset matrix (~600 tasks, ~$20, ~20 min):
python -m benchmarks.run --dataset all --arm all --tier subset --budget 30

# Aggregate to RESULTS.md + figures:
python -m benchmarks.aggregate

# Update README's headline:
python -m benchmarks.publish
```

## Three arms

| Arm | What's sent to GPT | Tests the contribution of |
|---|---|---|
| `marks` | annotated image + marks JSON | the full SoMatic pipeline |
| `coords` | raw image + marks JSON (no overlay) | structural detection alone |
| `raw` | raw image only | a pure VLM with no SoMatic at all |

The delta from `coords` → `marks` measures the value of the visual annotation specifically; the delta from `raw` → `coords` measures the value of structural detection.

## Two-tier execution

`--tier subset` runs a deterministic stratified ~200-sample slice per dataset (IDs pinned in `benchmarks/subsets/*-v1.json` after the first run). Use this for prompt iteration.

`--tier full` runs the entire dataset. Reserve for final numbers; expect 1.5k + 6.1k = 7.7k tasks per arm and ~$50–$150 per arm at current GPT-5.5 pricing.

## Cost guards

- `--budget USD` — runner aborts cleanly if cost exceeds this.
- `--dry-run` — exactly one task per (dataset, arm) for smoke testing.
- `--max-tasks N` — cap.
- `--resume <jsonl>` — pick up where a crashed run left off (skips completed task IDs).

## Model selection

The harness defaults to `gpt-5.5`. To use a different model, set `SOMATIC_BENCH_MODEL`:

```sh
SOMATIC_BENCH_MODEL=gpt-5-pro python -m benchmarks.run ...
```

The runner makes a 1-token probe call at startup to verify the model is callable; it refuses to start (and prints `OPENAI_MODEL_INVALID`) if the id 404s.

## Outputs

- `benchmarks/results/raw/<dataset>__<arm>__<tier>__<timestamp>.jsonl` — one row per task.
- `benchmarks/results/raw/<...>.manifest.json` — model, pricing snapshot, timestamps.
- `benchmarks/results/RESULTS.md` — aggregated report.
- `benchmarks/results/figures/<dataset>.png` — bar chart per dataset.

The raw JSONL dir is gitignored; only RESULTS.md and the figures land in version control.

## Refusal-spatial handling

VenusBench-GD's `refusal_spatial` task type asks the agent to refuse impossible instructions. Since a raw VLM told to return `{x, y}` will almost always emit a coordinate, the aggregator reports refusal as a **separate sub-score** and **excludes it from the headline VenusBench-GD average**. The full per-task-type breakdown still shows it for all three arms.

## License

`benchmarks/` is MIT, same as the SoMatic CLI. Datasets are downloaded from Hugging Face at run time and are MIT-licensed. No redistribution happens at our layer.
