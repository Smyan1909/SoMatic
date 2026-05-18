# SoMatic

SoMatic is an agent-first CLI for native desktop UI automation. It wraps PyAutoGUI in a JSON-first command surface and adds Set-of-Marks screenshots so agents can click visible UI elements by ID instead of guessing coordinates.

The public binary is `somatic`. The planned npm package name is `@somatic/cli`.

## Install

```sh
npm install -g @somatic/cli
```

The npm package launches the Python core. Python 3.10+ must be available on `PATH`.
During npm postinstall, SoMatic creates a package-local virtualenv at `.venv/` and `pip install`s the local source with the `[vision]` extra (~30 MB). Opt-outs:

- `SOMATIC_SKIP_POSTINSTALL=1` — skip everything; install just the JS shim.
- `SOMATIC_SKIP_PYTHON_BOOTSTRAP=1` — skip the venv + pip install.
- `SOMATIC_SKIP_VISION=1` — install without the `[vision]` extra (annotated screenshots will not work; raw screenshots still do).

The `[vision]` extra pulls `onnxruntime`, `numpy`, and `huggingface-hub`. Importantly it does **not** pull `torch` or `ultralytics` — those are AGPL-3.0 (or pull in AGPL deps) and we keep them out of the MIT distribution. The pre-converted YOLO ONNX is downloaded at runtime via `somatic vision init`; see the **Licensing** section below for the AGPL implications.

For Python-only installs (no npm shim):

```sh
pip install -e .[vision]                       # runtime only (~30 MB)
pip install -e .[vision,mcp]                   # add the MCP server (Claude Code, Cursor, Continue)
```

See [docs/mcp.md](docs/mcp.md) for Claude Code wiring.

## Core Workflow

```sh
somatic doctor
somatic vision init
somatic screenshot --annotate
somatic click 3
somatic type "hello from SoMatic"
somatic hotkey ctrl s
somatic vision stop
```

`somatic vision init` is required before `--annotate` works. The first invocation downloads the OmniParser icon-detect YOLO weights and (if no pre-converted ONNX is configured) exports them to ONNX. Subsequent invocations reuse the cached file. The model stays resident in a background daemon until you call `somatic vision stop`, which frees memory.

Every command returns JSON. Screenshots are written to the SoMatic cache directory and the latest mark map is stored in a session cache.

## Commands

- `somatic screenshot [--annotate]`
- `somatic click <id|x,y>`
- `somatic double-click <id|x,y>`
- `somatic right-click <id|x,y>`
- `somatic middle-click <id|x,y>`
- `somatic mouse-down [id|x,y]`
- `somatic mouse-up [id|x,y]`
- `somatic move <id|x,y>`
- `somatic drag <id|x,y>`
- `somatic scroll <amount> [--target <id|x,y>]`
- `somatic type "text"`
- `somatic write "text"`
- `somatic hotkey ctrl s`
- `somatic press enter`
- `somatic key-down shift`
- `somatic key-up shift`
- `somatic wait 1`
- `somatic position`
- `somatic size`
- `somatic locate image.png [--all]`
- `somatic center image.png`
- `somatic windows active|list`
- `somatic failsafe [--enable|--disable]`
- `somatic pause 0.1`
- `somatic doctor`
- `somatic bootstrap`
- `somatic vision init|stop|status`
- `somatic click-near <id|x,y> [--dx N] [--dy N]`
- `somatic mcp serve` (stdio MCP server — see [docs/mcp.md](docs/mcp.md))
- `somatic skill` (prints the operating-loop guidance)
- `somatic headless start|stop|status|launch` (Linux only — see [docs/headless.md](docs/headless.md))

## Platform Notes

Windows requires an interactive desktop session. Elevated applications may require an elevated terminal or agent host.

macOS requires Accessibility and Screen Recording permissions for the terminal or host app running SoMatic.

Linux works best on X11. Wayland compositors may block screenshot or pointer control unless desktop-specific permissions are configured.

## Vision

The vision daemon exposes a local HTTP API:

- `GET /health` — daemon status, weights path, PID
- `POST /parse` with `{ "image_path": "/absolute/path.png" }` — runs YOLO ONNX inference, returns `{ marks: [...], provider: "yolo-onnx", inference_ms: ... }`

Marks contain `id`, `bbox` (`[x1, y1, x2, y2]` in image pixels), `center` (`[x, y]`), and `confidence`. There are no captions or OCR text — agents act on numbered boxes and resolve coordinates via the mark id.

By default `somatic screenshot` and `somatic screenshot --annotate` also embed the captured PNGs as base64 in the JSON response (`image_b64`, `annotated_image_b64`) so agents that consume base64 image content can pick them up in the same call. Pass `--no-image` to opt out.

Tuning knobs (env vars):

- `SOMATIC_YOLO_CONF` (default `0.10`) — detection confidence threshold
- `SOMATIC_YOLO_IOU` (default `0.45`) — NMS IoU threshold
- `SOMATIC_YOLO_ONNX_REPO` — Hugging Face repo holding a pre-converted ONNX; if unset, `vision init` downloads the upstream `.pt` and converts on first run
- `SOMATIC_YOLO_ONNX_PATH` — point at a local ONNX file to skip download/conversion (useful for development)

See [platform setup](docs/platforms.md) and [release checklist](docs/release.md).

## Headless (Linux)

On Linux, SoMatic can spawn an Xvfb virtual desktop so actions run on a sandbox display rather than your real screen:

```sh
somatic headless start --launch discord --vnc
somatic screenshot --annotate    # operates on the virtual desktop
somatic headless stop
```

See [docs/headless.md](docs/headless.md) for prerequisites and the full walkthrough.

## Licensing

SoMatic follows the **FFmpeg licensing strategy**: a strictly MIT-licensed core, with AGPL-licensed conversion tooling segregated into a separate directory so it never touches the published artifacts.

- **`src/somatic/`** — MIT. The CLI, MCP server, vision daemon, automation primitives, and the YOLO ONNX inference path. Zero AGPL imports. A pytest-time check (`tests/test_license_boundary.py`) fails CI if anyone re-adds `import ultralytics` here.
- **YOLO ONNX weights** — AGPL-3.0. Derived from `microsoft/OmniParser-v2.0`'s upstream YOLO checkpoint. SoMatic does not bundle the weights; `somatic vision init` downloads them at runtime from a separately-licensed Hugging Face repository. Run `somatic license` for the full notice.
- **`tools/`** — AGPL-3.0. The `convert_yolo_to_onnx.py` script imports `ultralytics` (AGPL-3.0) and produces an AGPL-3.0 ONNX file. This directory is excluded from both the npm tarball and the PyPI sdist/wheel; it ships only via the source repository for maintainers and power users. See [`tools/README.md`](tools/README.md).

Practically: if you `pip install -e .` or `npm install -g @somatic/cli`, your install is MIT. The moment you run `somatic vision init` you accept the AGPL-3.0 obligations on the downloaded weights. If you run anything from `tools/`, your derivative ONNX is also AGPL-3.0.
