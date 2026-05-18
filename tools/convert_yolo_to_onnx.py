"""
AGPL-3.0-licensed tool — license boundary file.

This script imports `ultralytics`, which is licensed under GNU AGPL-3.0.
Running this script produces a converted `.onnx` file that is itself
AGPL-3.0 (inherited from the upstream OmniParser `icon_detect` weights).

The SoMatic CLI in `src/somatic/` does NOT import this script and is
distributed under the MIT License. This script is provided in `tools/`
specifically so that the MIT-licensed runtime never has to load AGPL code
to keep its license boundary clean.

Run this script only if you understand and accept AGPL-3.0 obligations on
your derivative outputs. See `tools/LICENSE.AGPL` and `tools/README.md`.

Typical maintainer invocation (one-time per release):

    cd tools/
    pip install -r requirements.txt
    python convert_yolo_to_onnx.py --output ../build/icon-detect.onnx --emit-sha256
    # Upload both ../build/icon-detect.onnx and ../build/icon-detect.onnx.sha256
    # to the SoMatic Hugging Face repo.

Typical end-user invocation (only needed if you can't or won't use the
pre-converted ONNX from Hugging Face):

    cd tools/
    pip install -r requirements.txt
    python convert_yolo_to_onnx.py --output icon-detect.onnx
    # Then: export SOMATIC_YOLO_ONNX_PATH=$(realpath icon-detect.onnx)
    # and run `somatic vision init` — it will pick up the local file.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

# Source repo / file for the upstream YOLO checkpoint.
DEFAULT_PT_REPO = "microsoft/OmniParser-v2.0"
DEFAULT_PT_FILENAME = "icon_detect/model.pt"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="convert_yolo_to_onnx.py",
        description=(
            "Convert the OmniParser icon_detect YOLO .pt checkpoint to ONNX. "
            "This tool uses AGPL-licensed dependencies (ultralytics). The "
            "produced .onnx inherits AGPL-3.0 from upstream YOLO."
        ),
    )
    parser.add_argument("--pt-repo", default=DEFAULT_PT_REPO,
                        help=f"Hugging Face repo to fetch the .pt from (default: {DEFAULT_PT_REPO}).")
    parser.add_argument("--pt-filename", default=DEFAULT_PT_FILENAME,
                        help=f"Filename within the repo (default: {DEFAULT_PT_FILENAME}).")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--opset", type=int, default=12)
    parser.add_argument("--output", type=Path, default=Path("build/icon-detect.onnx"),
                        help="Destination .onnx path.")
    parser.add_argument("--keep-pt", action="store_true",
                        help="Keep the downloaded .pt next to the ONNX output.")
    parser.add_argument("--emit-sha256", action="store_true",
                        help="Write a companion `<output>.sha256` file with the hex digest. "
                             "The SoMatic runtime verifies against this sidecar when fetching "
                             "the ONNX from Hugging Face.")
    args = parser.parse_args(argv)

    print("=" * 72)
    print("AGPL-3.0 conversion tool (see tools/LICENSE.AGPL).")
    print("Outputs inherit AGPL-3.0 from upstream YOLO weights.")
    print("=" * 72)
    print()

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("Install huggingface-hub: pip install -r tools/requirements.txt", file=sys.stderr)
        return 1
    try:
        from ultralytics import YOLO
    except ImportError:
        print(
            "Install ultralytics (AGPL-3.0): pip install -r tools/requirements.txt",
            file=sys.stderr,
        )
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    workdir = args.output.parent / "_convert"
    workdir.mkdir(parents=True, exist_ok=True)
    staging_pt = workdir / "icon-detect.pt"

    print(f"Downloading {args.pt_filename} from {args.pt_repo}...")
    pt_path = Path(hf_hub_download(repo_id=args.pt_repo, filename=args.pt_filename))
    shutil.copyfile(pt_path, staging_pt)

    print(f"Exporting to ONNX (imgsz={args.imgsz}, opset={args.opset})...")
    model = YOLO(str(staging_pt))
    exported = model.export(format="onnx", imgsz=args.imgsz, opset=args.opset, simplify=True, dynamic=False)

    exported_path = Path(exported) if isinstance(exported, (str, Path)) else staging_pt.with_suffix(".onnx")
    if not exported_path.exists():
        print(f"Ultralytics did not produce an ONNX file at {exported_path}", file=sys.stderr)
        return 1
    shutil.move(str(exported_path), args.output)

    size = args.output.stat().st_size
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()

    if args.keep_pt:
        shutil.move(str(staging_pt), args.output.with_suffix(".pt"))
    shutil.rmtree(workdir, ignore_errors=True)

    if args.emit_sha256:
        sha_path = args.output.with_name(args.output.name + ".sha256")
        sha_path.write_text(f"{digest}  {args.output.name}\n", encoding="utf-8")
    else:
        sha_path = None

    print()
    print(f"Output:  {args.output}")
    print(f"Size:    {size:,} bytes")
    print(f"SHA256:  {digest}")
    if sha_path:
        print(f"Sidecar: {sha_path}")
    print()
    print("Maintainer: upload `icon-detect.onnx` AND `icon-detect.onnx.sha256`")
    print("to the SoMatic Hugging Face repo (model card must note AGPL-3.0).")
    print()
    print("End-user: export SOMATIC_YOLO_ONNX_PATH=" + str(args.output.resolve()))
    print("Then run `somatic vision init` — it will pick up the local file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
