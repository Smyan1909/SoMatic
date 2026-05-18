from __future__ import annotations

import os
from pathlib import Path

try:
    from platformdirs import user_cache_dir, user_config_dir, user_data_dir
except Exception:  # pragma: no cover - used before package dependencies are installed
    def _base_dir(kind: str) -> str:
        if os.name == "nt":
            root = os.environ.get("LOCALAPPDATA") if kind == "cache" else os.environ.get("APPDATA")
            return str(Path(root or Path.home() / "AppData" / "Local") / APP_NAME)
        if kind == "config":
            return str(Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME)
        if kind == "data":
            return str(Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME)
        return str(Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / APP_NAME)

    def user_cache_dir(appname: str) -> str:
        return _base_dir("cache")

    def user_config_dir(appname: str) -> str:
        return _base_dir("config")

    def user_data_dir(appname: str) -> str:
        return _base_dir("data")

APP_NAME = "somatic"


def cache_dir() -> Path:
    path = Path(os.environ.get("SOMATIC_CACHE_DIR", user_cache_dir(APP_NAME)))
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_dir() -> Path:
    path = Path(os.environ.get("SOMATIC_DATA_DIR", user_data_dir(APP_NAME)))
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_dir() -> Path:
    path = Path(os.environ.get("SOMATIC_CONFIG_DIR", user_config_dir(APP_NAME)))
    path.mkdir(parents=True, exist_ok=True)
    return path


def screenshot_dir() -> Path:
    path = cache_dir() / "screenshots"
    path.mkdir(parents=True, exist_ok=True)
    return path


def session_file(session: str = "default") -> Path:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in session)
    return cache_dir() / f"marks-{safe}.json"


def daemon_pid_file() -> Path:
    return cache_dir() / "vision-daemon.pid"


def daemon_log_file() -> Path:
    return cache_dir() / "vision-daemon.log"


def yolo_weights_dir() -> Path:
    path = data_dir() / "yolo"
    path.mkdir(parents=True, exist_ok=True)
    return path


def onnx_weights_path() -> Path:
    return yolo_weights_dir() / "icon-detect.onnx"


def onnx_weights_source_file() -> Path:
    return yolo_weights_dir() / "icon-detect.source.json"


def legacy_omniparser_dir() -> Path:
    return data_dir() / "omniparser"


def headless_state_file() -> Path:
    return cache_dir() / "headless_state.json"


def headless_log_file() -> Path:
    return cache_dir() / "headless.log"


def headless_xauth_file() -> Path:
    return cache_dir() / "headless.Xauthority"
