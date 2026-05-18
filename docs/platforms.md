# Platform Setup

SoMatic controls the active native desktop session. It needs the same permissions a human-driven automation tool needs.

## Windows

- Run SoMatic inside an interactive desktop session.
- If automating elevated applications, run the terminal or agent host with matching elevation.
- Remote/headless sessions may expose a different desktop than the one you are looking at.

## macOS

Grant permissions to the terminal or agent host that launches SoMatic:

- Accessibility for pointer and keyboard automation.
- Screen Recording for screenshots.

After changing permissions, restart the terminal or agent host.

## Linux

X11 is the most reliable backend for PyAutoGUI. Wayland compositors may block screen capture or pointer control by design.

Recommended alpha setup:

- Use an X11 session where possible.
- Confirm `DISPLAY` is set.
- If using Wayland, expect compositor-specific limitations.

## Vision Runtime

`somatic vision init` starts a small local daemon that loads the OmniParser icon-detect YOLO model under `onnxruntime`. The daemon runs on `127.0.0.1:8765` and listens for `/parse` requests from `somatic screenshot --annotate`. The model file (~10–15 MB) is cached under SoMatic's data directory and reused across sessions.

The very first `vision init` after install downloads `icon_detect/model.pt` from `microsoft/OmniParser-v2.0` and exports it to ONNX using `ultralytics`. This is one-time; later inits skip straight to loading the cached `.onnx`.

`somatic vision stop` terminates the daemon and frees the model's memory. The cached weights remain on disk for the next `vision init`.

A GPU is **not** required. Inference runs on CPU and typically returns boxes in under 300 ms on a 1920×1080 screenshot.
