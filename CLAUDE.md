# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

SoMatic is an agent-first CLI for native desktop UI automation using Set-of-Marks (SoM) screenshot technology. It exposes a JSON-only command interface (`somatic <command>`) that AI agents use to control native desktop UIs — clicking, typing, scrolling, and capturing annotated screenshots where UI elements are numbered for reference.

Mark resolution is purely id → coordinate. Marks carry no captions or OCR text; agents act on numbered boxes and the click path looks up the center of the chosen mark from a cached session JSON.

## Commands

```bash
# Install Python package (run once)
pip install -e .[dev,vision,mcp]

# Run all tests
python -m pytest

# Run a single test file
python -m pytest tests/test_yolo_onnx_provider.py

# Run a single test by name
python -m pytest tests/test_cli.py::test_wait_outputs_json -q

# npm postinstall / shim validation
node bin/somatic.js doctor
npm run pack:check
```

The `[vision]` extra installs `onnxruntime`, `numpy`, `huggingface-hub`, plus `ultralytics`+`torch` (used only by the first-run `.pt → .onnx` conversion fallback).

## Architecture

SoMatic has **three agent-facing surfaces** that share the same underlying modules, plus two long-lived background processes that they orchestrate:

1. **Plain CLI** (`somatic <command>`) — universal fallback for any harness that can shell out. JSON to stdout; for screenshots the JSON now includes `image_b64`/`annotated_image_b64` so the bytes can be fed to the model without a separate Read step.
2. **MCP server** (`somatic mcp serve` or `python -m somatic.mcp_server`) — for Claude Code / Cursor / Continue. Tools mirror the CLI verbs; screenshot tools emit MCP `ImageContent` + `TextContent` so the agent sees the image inline. Ships a `skill` MCP prompt that loads the operating loop.
3. **Vision daemon** (`vision_init` / `vision_stop`) — long-lived background process that holds the YOLO ONNX model. Both the CLI and MCP server talk to it over HTTP on `127.0.0.1:8765`.
4. **Headless session** (`headless start` / `headless stop`, Linux only) — long-lived Xvfb + WM + optional VNC + optional apps. When active, every other CLI invocation transparently inherits `DISPLAY` / `XAUTHORITY` / `DBUS_SESSION_BUS_ADDRESS` via `headless.apply_active_env()` at the top of `main()`. The vision daemon is auto-restarted under the headless display so screenshots come from the virtual desktop.

A thin Node.js shim (`bin/somatic.js`) spawns the Python CLI for npm-installed users; it's a pure passthrough.

```
bin/somatic.js          Node shim — resolves Python, sets PYTHONPATH=src/, spawns
scripts/postinstall.js  npm postinstall: creates .venv, pip installs .[vision]
src/somatic/            MIT-licensed runtime. ZERO AGPL imports (CI-enforced).
  cli.py                Argparse dispatcher — calls headless.apply_active_env() first
  mcp_server.py         FastMCP wrapper exposing the same surface as MCP tools+prompt
  skill.py              Single source of truth for SKILL.md content (used by CLI+MCP)
  licenses.py           Static MIT/AGPL notices used by `somatic license` + MCP prompt
  SKILL.md              Packaged operating-loop guidance (shipped in the wheel)
  automation.py         PyAutoGUI wrappers (click, click_near, type, move, drag, scroll, hotkey…)
  screenshot.py         Capture + annotation; embeds base64 PNG bytes in response
  marks.py              Mark dataclass, session cache (JSON file), normalize_marks()
  vision_client.py      HTTP client for the local vision daemon (GET /health, POST /parse)
  vision_daemon.py      Background process: loads ONNX model, serves on 127.0.0.1:8765
  providers/yolo_onnx.py  Pure inference; SHA256-verified HF download; no .pt→.onnx convert
  headless.py           Xvfb session lifecycle, state-file glue, env overlay
  doctor.py             Platform diagnostics (dependency checks, failsafe tests)
  paths.py              XDG-compliant runtime paths (cache, data, screenshots, PID files)
  jsonio.py             command_response(), SomaticError, fail() — all CLI output goes here
tools/                  AGPL-3.0-licensed boundary. NOT shipped in npm or PyPI.
  LICENSE.AGPL          Full AGPL-3.0 text
  README.md             License-boundary explanation
  requirements.txt      ultralytics + torch (AGPL-3.0 deps)
  convert_yolo_to_onnx.py  Maintainer/power-user .pt → .onnx conversion
tests/                  Including test_license_boundary.py which CI-enforces the MIT/AGPL split
```

### Licensing boundary

The repo follows the FFmpeg licensing strategy:

- The published artifacts (`npm install -g @somatic/cli` and PyPI wheel/sdist) are pure MIT.
- The model weights are AGPL-3.0 (inherited from upstream YOLO). They are downloaded at runtime from a separately-licensed Hugging Face repository via `somatic vision init`; SoMatic never bundles them.
- The conversion tool that converts the upstream `.pt` to `.onnx` lives under `tools/`. It imports `ultralytics` (AGPL-3.0) and produces AGPL-3.0 outputs. `tools/` is excluded from both npm and PyPI by `package.json`'s `files` allowlist, `.npmignore`, and `pyproject.toml`'s sdist exclude list.
- `tests/test_license_boundary.py` runs in CI on every commit and fails the build if any module under `src/somatic/` either statically imports `ultralytics` or transitively pulls it into `sys.modules`.

**Critical invariant**: every code path must exit through `jsonio.command_response()` or `jsonio.fail()`. The CLI never prints prose — callers are AI agents expecting machine-readable JSON.

### Annotated screenshot flow

1. Agent has previously run `somatic vision init`, which spawned `python -m somatic.vision_daemon serve` on `127.0.0.1:8765`. The daemon loaded `icon-detect.onnx` once and is now ready.
2. `screenshot.py:screenshot()` → `capture_raw()` saves a PIL screenshot to the cache dir.
3. `vision_client.py:parse_screenshot()` → HTTP POST to `localhost:8765/parse` with `{image_path}`.
4. `vision_daemon.DaemonHandler.do_POST()` → `yolo_onnx.parse(session, path)`.
5. `yolo_onnx.parse()`: PIL open → letterbox to 640×640 → `onnxruntime` session.run → confidence filter → NMS → reverse letterbox → sort marks top-to-bottom, left-to-right → return `{provider, marks, inference_ms}`.
6. `marks.py:normalize_marks()` validates the dict shape against the `Mark` dataclass.
7. `screenshot.py:annotate_image()` draws red numbered rectangles on the original image.
8. `marks.py:save_marks()` writes the mark map to `cache/marks-{session}.json`.
9. Returns full JSON with `screenshot`, `marks[]`, `annotated_path`, `provider`, `inference_ms`.

Subsequent commands like `somatic click 3` load the cached mark map and resolve the center coordinate from `marks.json` — no daemon round-trip needed for action commands.

### Vision daemon lifecycle

- `somatic vision init` — spawns the daemon process. If `data/yolo/icon-detect.onnx` does not exist, the daemon first attempts to download a pre-converted ONNX from the HF repo named in `SOMATIC_YOLO_ONNX_REPO`; if that is empty or unreachable, it falls back to downloading `icon_detect/model.pt` from `microsoft/OmniParser-v2.0` and running `ultralytics.YOLO(...).export(format="onnx")`. The provenance of the cached weights is recorded next to them in `icon-detect.source.json`. The daemon also wipes any stale `data/omniparser/` from prior installs.
- `somatic vision stop` — kills the daemon process (taskkill on Windows, SIGTERM elsewhere) and removes the PID file. The ONNX file stays on disk for next time.
- `somatic vision status` — GET `/health` and reports whether the daemon is reachable.

### Runtime directories (via `paths.py`)

| Platform | Cache | Data |
|----------|-------|------|
| Windows  | `%LOCALAPPDATA%\somatic` | `%APPDATA%\somatic` |
| Linux/macOS | `~/.cache/somatic` | `~/.local/share/somatic` |

Cache holds: screenshots, per-session mark JSON, `vision-daemon.pid`, `vision-daemon.log`.
Data holds: `yolo/icon-detect.onnx` and `yolo/icon-detect.source.json`.

## JSON Response Contract

Every command returns one JSON object. Callers must check `ok`:

```json
{ "ok": true,  "command": "click", "elapsed_ms": 45.2, ... }
{ "ok": false, "command": "click", "elapsed_ms": 5.1,
  "error": { "code": "mark_not_found", "message": "...", "details": {...} } }
```

Error codes are defined as `SomaticError` instances raised through `jsonio.fail()`. When adding new error conditions, name them clearly (e.g., `yolo_onnx_missing`, `vision_unavailable`) rather than reusing generic codes.

## Configuration knobs (env vars)

- `SOMATIC_YOLO_CONF` — detection confidence threshold (default `0.10`)
- `SOMATIC_YOLO_IOU` — NMS IoU threshold (default `0.45`)
- `SOMATIC_YOLO_INPUT_SIZE` — letterbox size (default `640`)
- `SOMATIC_YOLO_THREADS` — onnxruntime intra-op thread count
- `SOMATIC_YOLO_ONNX_REPO` / `SOMATIC_YOLO_ONNX_FILENAME` — HF repo + filename for the pre-converted ONNX
- `SOMATIC_YOLO_ONNX_PATH` — local override pointing at an `.onnx` file (skips download/conversion entirely)
- `SOMATIC_VISION_URL` — override the daemon URL clients connect to
- `SOMATIC_VISION_PORT` — override the daemon listen port
- `SOMATIC_VISION_INIT_TIMEOUT` — seconds to wait for the daemon to come ready (default `600`)

## Testing

Tests live in `tests/`. pytest is configured in `pyproject.toml` with `pythonpath = ["src"]` so imports work without installation. `test_yolo_onnx_provider.py` exercises inference logic with a `_FakeSession` stub so tests do not need a real ONNX model. `test_vision_daemon.py` boots the HTTP handler on a random port with a fake session.

The CI matrix runs Python 3.12 on Linux, macOS, and Windows — be mindful of path separators and PyAutoGUI display requirements (Linux CI needs a virtual display).
