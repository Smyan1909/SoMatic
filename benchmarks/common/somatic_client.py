"""In-process SoMatic adapter for the benchmark harness.

Imports `somatic.providers.yolo_onnx` directly so each benchmark task can
share a single long-lived ONNX `InferenceSession`. This avoids the
~5–10 ms per-task overhead of the daemon HTTP layer, which compounds to
several minutes across a 23k-task full-tier run.

For end-to-end CLI testing, `--via-cli` swaps in a subprocess wrapper that
calls `python -m somatic.cli screenshot --annotate --input <tmpfile>` and
parses the resulting JSON.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SomaticResponse:
    marks: list[dict[str, Any]]
    annotated_image_b64: str
    raw_image_b64: str
    inference_ms: float


class InProcessSomaticClient:
    """Loads the YOLO ONNX model once at construction and reuses the session.

    Requires SOMATIC_YOLO_ONNX_PATH or SOMATIC_YOLO_ONNX_REPO to be set so
    `somatic.providers.yolo_onnx.ensure_weights()` can resolve a model.
    """

    def __init__(self) -> None:
        from somatic.providers import yolo_onnx
        from somatic.screenshot import annotate_image

        self._yolo = yolo_onnx
        self._annotate_image = annotate_image
        self._ensure_weights = yolo_onnx.ensure_weights
        self._session = None  # lazy

    def _get_session(self):
        if self._session is None:
            self._ensure_weights()
            from somatic.paths import onnx_weights_path

            self._session = self._yolo.load_session(onnx_weights_path())
        return self._session

    def infer(self, image_bytes: bytes) -> SomaticResponse:
        from PIL import Image

        # Write to a tmp file so we can reuse `annotate_image` (which expects
        # a path) without changing SoMatic's public surface.
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            src = tmpdir_path / "in.png"
            src.write_bytes(image_bytes)

            t0 = time.perf_counter()
            parsed = self._yolo.parse(self._get_session(), src)
            inference_ms = (time.perf_counter() - t0) * 1000.0

            # Annotate using SoMatic's own drawer for parity with `--annotate`.
            from somatic.marks import normalize_marks

            marks = normalize_marks(parsed.get("marks", []))
            # `annotate_image` writes alongside `src`; pass the renamed
            # source so the resulting file lives in our tmpdir.
            annotated_src = tmpdir_path / "screenshot-bench.png"
            annotated_src.write_bytes(image_bytes)
            annotated_path = self._annotate_image(annotated_src, marks, output_dir=tmpdir_path)
            annotated_bytes = Path(annotated_path).read_bytes()

        return SomaticResponse(
            marks=marks,
            annotated_image_b64=base64.b64encode(annotated_bytes).decode("ascii"),
            raw_image_b64=base64.b64encode(image_bytes).decode("ascii"),
            inference_ms=inference_ms,
        )


class CliSomaticClient:
    """End-to-end CLI fallback. Spawns `python -m somatic.cli screenshot
    --annotate --input <tmpfile>` per task. Useful for one-off sanity tests
    of the public surface; slow for full-tier runs."""

    def infer(self, image_bytes: bytes) -> SomaticResponse:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            src = tmpdir_path / "in.png"
            src.write_bytes(image_bytes)
            t0 = time.perf_counter()
            proc = subprocess.run(  # noqa: S603,S607
                [
                    sys.executable,
                    "-m",
                    "somatic.cli",
                    "screenshot",
                    "--annotate",
                    "--input",
                    str(src),
                    "--output-dir",
                    str(tmpdir_path),
                ],
                check=True,
                capture_output=True,
                env={**os.environ, "SOMATIC_HEADLESS_DISABLE": "1"},
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
        payload = json.loads(proc.stdout.decode("utf-8"))
        return SomaticResponse(
            marks=payload.get("marks", []),
            annotated_image_b64=payload.get("annotated_image_b64", ""),
            raw_image_b64=payload.get("image_b64", base64.b64encode(image_bytes).decode("ascii")),
            inference_ms=elapsed_ms,
        )
