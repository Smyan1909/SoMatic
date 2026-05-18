#!/usr/bin/env bash
# Publish the SoMatic pre-converted YOLO ONNX to a Hugging Face repo.
#
# This script lives in the AGPL-licensed tools/ directory because it invokes
# convert_yolo_to_onnx.py, which imports ultralytics (AGPL-3.0). The output
# .onnx is AGPL-3.0 (inherited from upstream YOLO).
#
# Prerequisites (one-time):
#   pip install -r requirements.txt        # installs ultralytics + torch
#   hf auth login                          # interactive HF token prompt
#
# Usage:
#   ./publish.sh <hf-repo-id>
#
# Example:
#   ./publish.sh somatic-cli/icon-detect-onnx
#
# What it does:
#   1. Runs convert_yolo_to_onnx.py to produce icon-detect.onnx and
#      icon-detect.onnx.sha256 in ../build/.
#   2. Uploads both files to the named Hugging Face repo (creates if missing).
#   3. Reminds you to update the model card with the AGPL-3.0 declaration and
#      a copy of LICENSE.AGPL.
set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "usage: $0 <hf-repo-id>" >&2
    echo "  example: $0 somatic-cli/icon-detect-onnx" >&2
    exit 1
fi

REPO_ID="$1"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." &> /dev/null && pwd)"
OUT_DIR="${REPO_ROOT}/build"
ONNX_PATH="${OUT_DIR}/icon-detect.onnx"
SHA_PATH="${OUT_DIR}/icon-detect.onnx.sha256"

mkdir -p "${OUT_DIR}"

echo "================================================================="
echo "Publishing AGPL-3.0 weights to Hugging Face repo: ${REPO_ID}"
echo "================================================================="

if ! command -v hf > /dev/null 2>&1; then
    echo "[publish] 'hf' CLI not found. Install with: pip install -r requirements.txt" >&2
    exit 1
fi

if ! hf auth whoami > /dev/null 2>&1; then
    echo "[publish] Not logged in. Run: hf auth login" >&2
    exit 1
fi

echo "[publish] Converting .pt -> .onnx (this uses AGPL-licensed ultralytics) ..."
python "${SCRIPT_DIR}/convert_yolo_to_onnx.py" --output "${ONNX_PATH}" --emit-sha256

echo ""
echo "[publish] Uploading ${ONNX_PATH} ..."
hf upload "${REPO_ID}" "${ONNX_PATH}" icon-detect.onnx

echo "[publish] Uploading ${SHA_PATH} ..."
hf upload "${REPO_ID}" "${SHA_PATH}" icon-detect.onnx.sha256

echo ""
echo "[publish] Done. Final steps (manual):"
echo "  1. Open https://huggingface.co/${REPO_ID}"
echo "  2. Add LICENSE.AGPL to the repo (copy from tools/LICENSE.AGPL)."
echo "  3. Edit the model card to declare AGPL-3.0 and link upstream YOLO."
echo "  4. Set SOMATIC_YOLO_ONNX_REPO=${REPO_ID} in CI and docs."
