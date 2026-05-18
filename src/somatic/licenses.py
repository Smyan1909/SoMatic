"""Static license notices for SoMatic.

The SoMatic CLI is MIT-licensed. The YOLO icon-detect ONNX used for
Set-of-Marks annotations is derived from upstream weights that inherit
GNU AGPL-3.0. We surface that distinction here so users can make an
informed choice — and so that `somatic license` (CLI) and the `license`
MCP prompt have a single source of truth.
"""
from __future__ import annotations

_SOMATIC_LICENSE = (
    "SoMatic CLI is distributed under the MIT License. See LICENSE in the "
    "repository root."
)

_VISION_WEIGHTS_NOTICE = """\
The YOLO icon-detect ONNX model used for Set-of-Marks annotations is derived
from microsoft/OmniParser-v2.0's `icon_detect/model.pt`, which inherits the
GNU Affero General Public License (AGPL-3.0) from upstream YOLO. This means:

  * The model weights themselves are AGPL-3.0.
  * Distributing the weights or a derivative model is subject to AGPL-3.0.
  * SoMatic's MIT-licensed code does not import or redistribute the weights;
    they are downloaded at runtime from a separately-licensed Hugging Face
    repository when you run `somatic vision init`.

If you do not want AGPL-3.0 weights, do not run `somatic vision init` — the
non-annotated `somatic screenshot` and click-by-coordinate flows do not use
the model. To produce your own ONNX from the upstream `.pt`, use the
AGPL-licensed tooling at `tools/convert_yolo_to_onnx.py` (see `tools/README.md`).
"""


def somatic_license() -> str:
    """Return the MIT-license summary for the SoMatic CLI itself."""
    return _SOMATIC_LICENSE


def vision_weights_notice() -> str:
    """Return the AGPL-3.0 notice covering the YOLO ONNX weights."""
    return _VISION_WEIGHTS_NOTICE


def combined() -> str:
    """Convenience: SoMatic license + vision weights notice as one block."""
    return f"{_SOMATIC_LICENSE}\n\n{_VISION_WEIGHTS_NOTICE}"
