"""Update README.md's Benchmarks section from RESULTS.md.

Replaces the content between the sentinel HTML comments
`<!-- benchmarks-begin -->` and `<!-- benchmarks-end -->` with the current
headline table (Markdown stripped of figure references). Idempotent.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
RESULTS_MD = ROOT / "benchmarks" / "results" / "RESULTS.md"

BEGIN = "<!-- benchmarks-begin -->"
END = "<!-- benchmarks-end -->"


def _extract_headline(results_md: str) -> str:
    """Pull the headline table section (and a one-line summary) out of the
    full RESULTS.md so we can drop a compact summary into the README."""
    lines = results_md.splitlines()
    # Find the Headline section, take up to the next H2.
    out: list[str] = []
    in_headline = False
    for line in lines:
        if line.strip() == "## Headline":
            in_headline = True
            continue
        if in_headline and line.startswith("## "):
            break
        if in_headline:
            out.append(line)
    # Trim leading/trailing blanks
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    if not out:
        return "_No benchmark runs yet. See [benchmarks/results/RESULTS.md](benchmarks/results/RESULTS.md)._"

    block = ["SoMatic is evaluated on ScreenSpot-Pro and VenusBench-GD against two baselines",
             "(raw GPT; SoMatic-as-hints-only + GPT). Full numbers, per-platform breakdowns,",
             "and methodology in [benchmarks/results/RESULTS.md](benchmarks/results/RESULTS.md).",
             ""]
    block.extend(out)
    return "\n".join(block)


def update_readme(readme_text: str, replacement: str) -> str:
    pattern = re.compile(
        re.escape(BEGIN) + r".*?" + re.escape(END),
        re.DOTALL,
    )
    new_section = f"{BEGIN}\n{replacement}\n{END}"
    if not pattern.search(readme_text):
        raise SystemExit(
            f"README.md is missing the benchmarks sentinels ({BEGIN} / {END}). "
            "Add the Benchmarks section first."
        )
    return pattern.sub(new_section, readme_text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="benchmarks.publish")
    parser.add_argument("--commit", action="store_true", help="Commit README + RESULTS.md changes after writing.")
    args = parser.parse_args(argv)

    if not RESULTS_MD.exists():
        raise SystemExit(
            f"{RESULTS_MD} does not exist. Run `python -m benchmarks.aggregate` first."
        )

    results_md = RESULTS_MD.read_text(encoding="utf-8")
    headline = _extract_headline(results_md)

    readme = README.read_text(encoding="utf-8")
    updated = update_readme(readme, headline)
    if updated == readme:
        print("README.md is already up to date.")
    else:
        README.write_text(updated, encoding="utf-8")
        print(f"Updated {README}")

    if args.commit:
        import subprocess

        subprocess.run(
            ["git", "add", str(README), str(RESULTS_MD)],
            check=True,
            cwd=ROOT,
        )
        figures_dir = ROOT / "benchmarks" / "results" / "figures"
        if figures_dir.exists():
            subprocess.run(["git", "add", str(figures_dir)], check=True, cwd=ROOT)
        subprocess.run(
            ["git", "commit", "-m", "chore(benchmarks): refresh RESULTS.md and README headline"],
            check=True,
            cwd=ROOT,
        )
        print("Committed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
