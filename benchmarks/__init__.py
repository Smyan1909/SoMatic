"""SoMatic benchmark harness.

Runs SoMatic's Set-of-Marks pipeline + GPT-5.5 (and two baselines: SoMatic-as-
hints-only and raw GPT-5.5) over ScreenSpot-Pro and VenusBench-GD, produces
Acc@Center numbers, and emits a versioned RESULTS.md plus PNG figures.

This package is dev-time tooling and is intentionally excluded from npm and
PyPI distributions. See the project README's Licensing section for details.
"""

__all__ = []
