"""License boundary guards.

SoMatic's MIT distribution must never transitively import AGPL-licensed code.
If anyone re-adds an `import ultralytics` (or similar) under `src/somatic/`,
these tests fail loudly in CI before the code can ship.

The conversion path (.pt → .onnx) intentionally lives in `tools/`, which is
NOT shipped in the npm tarball or the PyPI sdist/wheel and is not imported
by any module under `src/somatic/`.
"""
from __future__ import annotations

import importlib
import pathlib
import re
import sys


def _clear_ultralytics_modules() -> None:
    """Drop any pre-imported ultralytics from sys.modules so we can detect
    a fresh transitive import accurately."""
    for name in list(sys.modules):
        if name == "ultralytics" or name.startswith("ultralytics."):
            del sys.modules[name]


def test_importing_somatic_does_not_pull_in_ultralytics():
    _clear_ultralytics_modules()

    # Import the public surface and the modules that have historically been
    # most likely to grow an ultralytics dependency.
    importlib.import_module("somatic")
    importlib.import_module("somatic.providers.yolo_onnx")
    importlib.import_module("somatic.vision_daemon")
    importlib.import_module("somatic.cli")
    importlib.import_module("somatic.screenshot")
    importlib.import_module("somatic.automation")
    importlib.import_module("somatic.headless")

    assert "ultralytics" not in sys.modules, (
        "AGPL boundary violation: importing somatic transitively imported "
        "`ultralytics`. All ultralytics use must live in tools/ (which is "
        "outside the MIT distribution)."
    )


def test_no_actual_ultralytics_import_statements_under_src_somatic():
    """The substring 'ultralytics' is OK in docstrings/comments (we point
    users at tools/ explicitly), but ACTUAL `import` statements are not.

    Scans source files directly rather than importing them. That way the
    test runs even on installations that don't have every optional extra
    (e.g. CI without `[mcp]` or `[vision]`) and still catches a static
    boundary violation.
    """
    pattern = re.compile(r"^\s*(import\s+ultralytics|from\s+ultralytics)", re.MULTILINE)
    src_dir = pathlib.Path(__file__).resolve().parent.parent / "src" / "somatic"
    assert src_dir.is_dir(), f"expected src directory at {src_dir}"

    violations: list[str] = []
    for py in src_dir.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        match = pattern.search(text)
        if match is not None:
            rel = py.relative_to(src_dir.parent.parent)
            violations.append(f"{rel}: {match.group(0).strip()!r}")

    assert not violations, (
        "AGPL boundary violation under src/somatic/. ultralytics imports must "
        "live in tools/ only. Offenders:\n  " + "\n  ".join(violations)
    )


def test_yolo_onnx_does_not_reference_convert_function():
    """`_convert_from_pt` was removed deliberately. Its presence would mean
    someone re-added an in-process conversion path."""
    from somatic.providers import yolo_onnx

    assert not hasattr(yolo_onnx, "_convert_from_pt"), (
        "`_convert_from_pt` should not exist in yolo_onnx.py. The conversion "
        "path lives in tools/convert_yolo_to_onnx.py (AGPL-licensed)."
    )


def test_ensure_weights_error_mentions_tools_directory(tmp_path, monkeypatch):
    """A fresh user without HF or env vars must see an error that points
    them at the AGPL-segregated conversion tool, not at silent fallback
    behaviour."""
    from somatic.jsonio import SomaticError
    from somatic.providers import yolo_onnx

    monkeypatch.delenv("SOMATIC_YOLO_ONNX_PATH", raising=False)
    monkeypatch.delenv("SOMATIC_YOLO_ONNX_REPO", raising=False)
    monkeypatch.setattr(yolo_onnx, "HF_ONNX_REPO_ID", "")

    target = tmp_path / "icon-detect.onnx"

    try:
        yolo_onnx.ensure_weights(target)
    except SomaticError as exc:
        assert exc.code == "yolo_onnx_unavailable"
        msg = exc.message
        assert "tools/convert_yolo_to_onnx.py" in msg
        assert "SOMATIC_YOLO_ONNX_REPO" in msg
        assert "SOMATIC_YOLO_ONNX_PATH" in msg
        return
    raise AssertionError("ensure_weights should have failed without any source configured")
