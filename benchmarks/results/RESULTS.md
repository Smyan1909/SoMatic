# SoMatic Benchmark Results

_Last updated: 2026-05-19T15:34:02Z • Models: gpt-5.5 • Tiers: subset_

## Headline

| Dataset                | SoMatic+marks+GPT | SoMatic+coords+GPT | Raw GPT | Reference                                                                              |
| ---------------------- | ----------------- | ------------------ | ------- | -------------------------------------------------------------------------------------- |
| screenspot-pro (n=200) | 68.5%             | 73.0%              | 52.0%   | OmniParser + GPT-4o = 39.6% (paper); verify on the live leaderboard before publishing. |
| venusbench-gd (n=171)  | 70.2%             | 78.4%              | 59.6%   | Dataset released Dec 2025; published baselines pending — see arXiv 2512.16501.         |

## ScreenSpot-Pro per-platform

| Platform | marks | coords | raw   |
| -------- | ----- | ------ | ----- |
| linux    | 66.7% | 83.3%  | 0.0%  |
| macos    | 66.2% | 64.9%  | 46.8% |
| windows  | 70.1% | 77.8%  | 58.1% |

## ScreenSpot-Pro per-group

| Group      | marks | coords | raw   |
| ---------- | ----- | ------ | ----- |
| CAD        | 78.8% | 84.8%  | 72.7% |
| Creative   | 63.6% | 70.5%  | 52.3% |
| Dev        | 57.9% | 55.3%  | 36.8% |
| OS         | 58.3% | 70.8%  | 33.3% |
| Office     | 89.7% | 82.8%  | 58.6% |
| Scientific | 65.6% | 78.1%  | 56.2% |

## VenusBench-GD per-task-type

| Task type            | marks | coords | raw   |
| -------------------- | ----- | ------ | ----- |
| element_grounding    | 67.3% | 75.0%  | 57.7% |
| functional_grounding | 73.9% | 65.2%  | 52.2% |
| reason_grounding     | 61.1% | 77.8%  | 58.3% |
| refusal_grounding    | 3.4%  | 6.9%   | 13.8% |
| spatial_grounding    | 69.7% | 81.8%  | 51.5% |
| visual_grounding     | 85.2% | 92.6%  | 81.5% |

## Latency & cost (across all runs)

| Arm    | Mean ms/task | Total cost USD | Tokens                     |
| ------ | ------------ | -------------- | -------------------------- |
| marks  | 19038        | $27.00         | 3,783,071 in / 269,613 out |
| coords | 16136        | $24.84         | 3,682,271 in / 214,442 out |
| raw    | 19110        | $20.68         | 2,468,490 in / 277,912 out |

## Methodology

- **Acc@Center** metric: predicted click point is correct iff it falls inside the ground-truth bbox.
- **Refusal-spatial** (VenusBench-GD): correct iff the agent emitted no coordinate. Reported as a separate sub-score; **excluded** from the headline VenusBench-GD average to keep the raw-GPT arm's score from being asymmetrically dragged down (raw GPT-5.5 told to return {x,y} will rarely refuse).
- **Stratified subset** of 200/dataset for the dev tier; full datasets for the final tier. Subsets are pinned in `benchmarks/subsets/*-v1.json` for reproducibility.
- **GPT image detail**: `original` (preserves dense-UI fidelity).
- **Temperature**: 0.0; responses parsed as `response_format=json_object`.
- Source code: [`benchmarks/`](.). One run per (dataset, arm, tier); the aggregator picks the latest timestamp per combo.

