# Headless Mode (Linux)

SoMatic's `headless` subcommand spawns an [Xvfb](https://www.x.org/releases/X11R7.6/doc/man/man1/Xvfb.1.xhtml) virtual X display so SoMatic actions operate on a sandboxed desktop instead of your real screen. Useful for:

- CI tests of UI automation.
- Long-running agent workflows on Linux servers without a physical display.
- Sandboxed dev iteration on a new SKILL or click sequence without taking over your laptop.

**Linux-only.** Xvfb has no equivalent on macOS or Windows; `somatic headless start` on either of those platforms returns `error.code = "headless_unsupported_platform"`.

## Prerequisites

Debian / Ubuntu:

```sh
sudo apt install xvfb openbox dbus-x11 x11-utils xauth x11vnc imagemagick
```

| Package | Purpose |
|---|---|
| `xvfb` | The virtual framebuffer X server |
| `openbox` | Lightweight window manager; needed for Electron apps to render correctly |
| `dbus-x11` | D-Bus session bus; required by modern apps like Discord |
| `xauth` | Generates the per-session `MIT-MAGIC-COOKIE-1` so other processes can connect |
| `x11-utils` | Provides `xdpyinfo` — useful for manual debugging (the SoMatic readiness probe is socket-based) |
| `x11vnc` | Optional: VNC bridge so you can attach a viewer to see what's happening |
| `imagemagick` | Optional: ad-hoc framebuffer dumps via `DISPLAY=:99 import -window root screen.png` |

Run `somatic doctor` afterwards to confirm everything is on `PATH`.

## Quick start

```sh
# Bring up a 1920x1080 virtual desktop with Discord pre-launched and VNC enabled
somatic headless start --launch discord --vnc

# Vision daemon is auto-bound to the new DISPLAY; annotated screenshots
# capture the virtual desktop rather than your real screen
somatic vision init
somatic screenshot --annotate

# Standard SoMatic verbs all operate on the virtual desktop
somatic click 12
somatic type "hello"

# Add another app mid-session
somatic headless launch firefox

# Tear it all down — kills VNC, Discord, Firefox, WM, Xvfb
somatic headless stop
```

To peek at the virtual desktop while it runs (after `--vnc` was used):

```sh
# On the headless host
ssh -L 5900:localhost:5900 me@host    # if remote
vncviewer 127.0.0.1:5900               # or any VNC client
```

VNC is bound to `localhost` only by default — no port is exposed to the network.

## Commands

| Command | Description |
|---|---|
| `somatic headless start [...]` | Spawn Xvfb + optional WM + optional VNC + optional apps |
| `somatic headless stop` | Kill everything and clean up locks / Xauth cookie / state file |
| `somatic headless status` | Active? Which display? Which apps were launched? |
| `somatic headless launch <cmd> [args...]` | Spawn another app inside the running session |

`headless start` accepts:

- `--display :99` — explicit display number (auto-picked in `:99..:199` if omitted)
- `--geometry 1920x1080x24` — virtual screen size and color depth
- `--wm openbox` / `--no-wm` — window manager binary, or skip entirely
- `--launch '<cmd>'` (repeatable) — apps to start inside the session; each value is shell-split via `shlex`
- `--vnc` and `--vnc-port 5900` — opt-in VNC bridge
- `--no-adopt-vision-daemon` — leave the vision daemon alone instead of restarting it under the new DISPLAY

## How it works

`headless start` does the following:

1. Picks an unused display number.
2. Generates an MIT magic cookie and writes it to `~/.cache/somatic/headless.Xauthority`.
3. Spawns `Xvfb :{N} -screen 0 WxHxD -nolisten tcp -auth <xauthority>`.
4. Waits for the X socket at `/tmp/.X11-unix/X{N}` to accept connections.
5. Launches a D-Bus session via `dbus-launch --sh-syntax`.
6. Spawns the window manager (`openbox` by default).
7. Optionally spawns `x11vnc -display :{N} -localhost -forever -shared`.
8. If a vision daemon is currently running on the real display, stops it and re-launches it under the new DISPLAY so its screenshots come from the virtual desktop.
9. Launches any `--launch` apps inside the session (with `--no-sandbox` added automatically for Electron-based apps like Discord/Slack/Obsidian).
10. Writes session state to `~/.cache/somatic/headless_state.json`.

Subsequent `somatic` invocations (`click`, `screenshot`, …) call `headless.apply_active_env()` at the top of `main()`, which reads the state file and overlays `DISPLAY` / `XAUTHORITY` / `DBUS_SESSION_BUS_ADDRESS` into `os.environ` before anything else runs. The MCP server does the same.

## Troubleshooting

**`xauth_missing` or `xvfb_missing`** — install the prerequisites above, then re-run.

**Electron / Discord still crashes with "chrome-sandbox" error.** SoMatic auto-adds `--no-sandbox` for a known list of Electron binaries (`discord`, `slack`, `obsidian`, `code`, `signal-desktop`, `*.AppImage`). If your app isn't on the list, prepend the flag explicitly: `somatic headless launch /opt/myapp/myapp --no-sandbox`.

**App tries to play audio and hangs.** Xvfb has no audio device. Most apps tolerate the missing PulseAudio server gracefully; if yours doesn't, install PulseAudio and start a null sink: `pulseaudio --start --load=module-null-sink`.

**`xvfb_not_ready` after 5 seconds.** Look at `~/.cache/somatic/headless.log` for the Xvfb stderr; common causes are a port collision on the chosen display (use `--display :100` to skip) or stale lock files in `/tmp/.X{N}-lock`. SoMatic only removes stale locks whose holder PID is dead, so a still-running prior Xvfb won't be killed silently.

**Vision daemon didn't pick up the new DISPLAY.** Re-run `somatic vision init` once the headless session is up. The daemon auto-inherits via `subprocess_env()`, but if it was already running outside of SoMatic, `headless start` won't touch it unless `--no-adopt-vision-daemon` was *not* set.

**Lock files left over after a crash.** `/tmp/.X{N}-lock` and `/tmp/.X11-unix/X{N}` are normally cleaned up by `headless stop`. If you SIGKILL Xvfb manually, the next `headless start` will remove the stale entries safely (only after confirming the holder PID is dead).

## Test isolation

The Python test suite sets `SOMATIC_HEADLESS_DISABLE=1` for the whole session via `tests/conftest.py`. That stops a developer's local headless session from leaking `DISPLAY=:99` into pytest's process and breaking unrelated tests. Set the same variable in CI if you want to be doubly sure.
