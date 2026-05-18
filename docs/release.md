# Release Checklist

Alpha release checklist for `@somatic/cli`.

## 1. Tests

```sh
python -m pytest
node bin/somatic.js wait 0
npm pack --dry-run
```

`tests/test_license_boundary.py` must be green — those tests guarantee that no AGPL-licensed code (e.g. `ultralytics`) is reachable from `src/somatic/`.

## 2. Verify tarball contents

```sh
npm pack
tar -tzf somatic-cli-0.1.0.tgz | sort
```

The listing must include `bin/`, `scripts/postinstall.js`, `src/somatic/**`, `docs/`, `pyproject.toml`, `README.md`, `LICENSE`. It must **NOT** include:

- `tools/` (AGPL-licensed)
- `tests/`
- `.venv/`, `.git/`, `.github/`
- A top-level `SKILL.md` (canonical lives at `src/somatic/SKILL.md`)

For a faster packaging smoke in CI:

```sh
SOMATIC_SKIP_POSTINSTALL=1 npm install -g ./somatic-cli-0.1.0.tgz
```

## 3. Local desktop smoke (Windows / macOS / Linux)

```sh
somatic doctor
somatic license          # confirm AGPL notice surfaces
somatic vision init      # downloads the ONNX from SOMATIC_YOLO_ONNX_REPO
somatic screenshot --annotate
somatic click 1 --dry-run
somatic vision stop
```

If `SOMATIC_YOLO_ONNX_REPO` is unset, `vision init` should fail with `yolo_onnx_unavailable` and the message must point users at `tools/convert_yolo_to_onnx.py`.

## 4. Publish a fresh pre-converted ONNX to Hugging Face

This is the **only** step where AGPL-licensed code is involved. It happens in `tools/` so the MIT distribution stays clean.

```sh
cd tools/
pip install -r requirements.txt    # installs ultralytics (AGPL-3.0) + torch
python convert_yolo_to_onnx.py \
    --output ../build/icon-detect.onnx \
    --emit-sha256

# Inspect:
ls -la ../build/icon-detect.onnx ../build/icon-detect.onnx.sha256
cat ../build/icon-detect.onnx.sha256
```

Upload **both files** to the SoMatic Hugging Face repo, and ensure the repo's model card includes:

- AGPL-3.0 license declaration.
- A copy (or pointer) of `tools/LICENSE.AGPL`.
- Provenance: derived from `microsoft/OmniParser-v2.0` `icon_detect/model.pt`.

```sh
huggingface-cli upload <repo-id> ../build/icon-detect.onnx
huggingface-cli upload <repo-id> ../build/icon-detect.onnx.sha256
```

Once published, set `SOMATIC_YOLO_ONNX_REPO=<repo-id>` in CI and the local smoke environment so the runtime path exercises the HF download + sidecar verification.

## 5. PyPI publish (optional)

```sh
hatch build
twine upload dist/*
```

The sdist and wheel are MIT-only — `pyproject.toml`'s `[tool.hatch.build.targets.sdist]` exclude list keeps `tools/`, `tests/`, and `scripts/` out.

## 6. npm publish

```sh
npm publish --access public
```

Publish only after the `@somatic` npm scope is owned by the maintainers.
