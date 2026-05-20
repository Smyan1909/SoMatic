# AGPL-licensed tooling for SoMatic

Everything in this directory uses or produces code/data covered by the **GNU Affero General Public License, version 3** (AGPL-3.0). The full license text is in [`LICENSE.AGPL`](LICENSE.AGPL).

**The SoMatic runtime CLI (`src/somatic/`) does not import any code from this directory.** SoMatic itself is MIT-licensed and runs inference on a pre-converted ONNX model downloaded at runtime from a separately-licensed Hugging Face repository. This directory exists for two audiences:

1. **Maintainers** who publish a new pre-converted ONNX to the SoMatic Hugging Face repo on every release.
2. **End users** who want to produce their own ONNX from the upstream OmniParser checkpoint and accept the resulting AGPL obligations on the output file.

If you don't need either of those, you can ignore this entire directory. The SoMatic install pipeline (`pip install -e .[vision]` or `npm install -g @somatic-cli/cli`) never touches `tools/`.

## Why this directory exists

The OmniParser icon-detect YOLO checkpoint is fine-tuned from Ultralytics YOLOv8. Both the original Ultralytics weights and Ultralytics' Python library are AGPL-3.0. To convert `icon_detect/model.pt` to `.onnx` we have to import `ultralytics`. If that import lived under `src/somatic/`, AGPL would be activated against the whole SoMatic distribution.

So we follow the **FFmpeg strategy**: ship a strictly MIT core, segregate AGPL-touching tooling into a clearly-labeled separate tree with its own license file, and require users to opt in by explicitly running scripts from this tree.

## Usage

```sh
cd tools/
pip install -r requirements.txt
python convert_yolo_to_onnx.py --output icon-detect.onnx --emit-sha256
# Now icon-detect.onnx and icon-detect.onnx.sha256 exist.
# To make SoMatic use the local file:
export SOMATIC_YOLO_ONNX_PATH=$(realpath icon-detect.onnx)
somatic vision init
```

The conversion takes 1–3 minutes on CPU. `--emit-sha256` writes a companion file that the SoMatic runtime verifies against when fetching the same model from Hugging Face.

## Maintainer release workflow

```sh
cd tools/
pip install -r requirements.txt
python convert_yolo_to_onnx.py --output ../build/icon-detect.onnx --emit-sha256
# Upload BOTH files to the SoMatic Hugging Face repo:
huggingface-cli upload <repo-id> ../build/icon-detect.onnx
huggingface-cli upload <repo-id> ../build/icon-detect.onnx.sha256
```

The model card in the Hugging Face repo must state AGPL-3.0 (a copy of `LICENSE.AGPL` is the recommended `LICENSE` file there).

## License

- This directory: AGPL-3.0 (see `LICENSE.AGPL`).
- Outputs (`icon-detect.onnx`, etc.): AGPL-3.0.
- The SoMatic CLI (everything outside this directory): MIT.
