"""Pin the npm + PyPI distribution exclusion of `benchmarks/`.

`benchmarks/` is dev-time tooling and must never end up in a published
artifact. This mirrors `tests/test_license_boundary.py`'s pattern of
static-text-scanning the manifests so the check runs without spawning
npm or hatch.
"""
from __future__ import annotations

import json
import pathlib
import re


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_benchmarks_not_in_package_json_files_allowlist():
    package_json = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
    files = package_json.get("files", [])
    assert files, "package.json must keep an explicit files allowlist"
    offenders = [entry for entry in files if "benchmarks" in entry.lower()]
    assert not offenders, (
        f"package.json files allowlist must NOT include benchmarks/. Offenders: {offenders}"
    )


def test_benchmarks_in_npmignore_defense_in_depth():
    npmignore_text = (REPO_ROOT / ".npmignore").read_text(encoding="utf-8")
    assert re.search(r"^benchmarks/\s*$", npmignore_text, re.MULTILINE), (
        ".npmignore must list `benchmarks/` (defense-in-depth even if "
        "package.json's files allowlist already excludes it)."
    )


def test_benchmarks_in_pyproject_sdist_exclude():
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    # The hatch sdist section sets exclude = [...] as a TOML array. Match the
    # exclude block specifically (not the include block which precedes it).
    # We require the block to appear after [tool.hatch.build.targets.sdist]
    # and to contain a benchmarks entry.
    sdist_header = "[tool.hatch.build.targets.sdist]"
    sdist_index = pyproject_text.find(sdist_header)
    assert sdist_index >= 0, (
        "pyproject.toml must have a [tool.hatch.build.targets.sdist] section"
    )
    sdist_body = pyproject_text[sdist_index:]
    exclude_match = re.search(r"exclude\s*=\s*\[(.*?)\]", sdist_body, flags=re.DOTALL)
    assert exclude_match, (
        "pyproject.toml's [tool.hatch.build.targets.sdist] must have an exclude block"
    )
    assert "benchmarks" in exclude_match.group(1), (
        "pyproject sdist exclude must list `benchmarks/`."
    )


def test_benchmarks_path_exists():
    # Sanity: the exclusion is meaningful only if the directory exists.
    assert (REPO_ROOT / "benchmarks" / "run.py").is_file()
