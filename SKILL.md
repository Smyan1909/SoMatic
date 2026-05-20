# SoMatic

Use SoMatic when you need to operate a native desktop UI with screenshots, mouse, and keyboard.

> If SoMatic is configured as an MCP server, annotated screenshots arrive **inline** as image content in the tool response — you do **not** need a separate Read step. If you're invoking the plain CLI, the same image bytes are returned base64-encoded in the JSON response under `image_b64` / `annotated_image_b64`; ingest them as image content directly.

## Operating Loop

1. **At the start of a session, run `vision_init` (MCP) or `somatic vision init` (CLI).** This loads the YOLO ONNX model into a background daemon. First-ever run may take 1–3 minutes; subsequent runs are near-instant. Require `"started": true` (or `"already_running": true`) before continuing.
2. **Always begin a task with `screenshot_annotated` / `somatic screenshot --annotate` and *visually inspect* the image.** Treat the annotated screenshot as your primary input. Before deciding how to act, scan every region — taskbar, dock, desktop icons, system tray, open windows — and identify which numbered mark corresponds to the element you want.
3. **Prefer clicks on visible elements over keyboard navigation.** If the target is already present in the annotated screenshot (a taskbar icon, a tab, a button, a link), click its mark id. Do **not** open Start menu / Run / search when the thing you want is already on screen.
4. **Use the keyboard for what keyboards are for, not as a shortcut around looking.** Keyboard is the right tool for:
   - typing free-form text (`type_text "hello"`)
   - key chords that aren't UI elements (`hotkey ctrl s`, `press enter`, `hotkey alt tab`)
   - launching something that genuinely isn't visible anywhere (then use Win+S, type, screenshot the results, click the best match by mark id — don't blind-press Enter)
5. Inspect the JSON returned by the screenshot tool: `marks` contains `id`, `bbox`, `center`, and `confidence`. There are no captions — refer to elements by id and verify visually.
6. Act by mark id whenever possible:
   - `click 4`
   - `move 7`
   - `scroll -5 --target 2`
7. When YOLO **doesn't** annotate the exact target — empty text inputs, fields that follow a labelled icon, gaps between buttons — use `click_near` with a `dx`/`dy` offset from the nearest visible mark:
   - `click_near 12 --dx 300 --dy 0` (300 px to the right of mark 12)
8. Use raw coordinates only as a last resort when no mark and no anchor exists:
   - `click 640,420`
9. **Re-screenshot after every consequential action.** Mark IDs are reassigned per screenshot — never apply an id from one screenshot to another screenshot's state.
10. **At the end of the session, run `vision_stop`** to free the model's memory.
11. If something goes wrong, run `doctor` and `vision_status`.

## Decision Rule: Click, Click-Near, or Type?

When choosing how to advance the task, ask: *what does the latest annotated screenshot show?*

- **Target visible as a mark →** `click <id>`. Don't open a launcher.
- **Target NOT visible as a mark but adjacent to one →** `click_near <id> --dx ... --dy ...`. (Common for text inputs that sit next to a `+` or send button.)
- **Target's container visible but not the target itself →** click into the container first, re-screenshot, then act on the new marks.
- **Target genuinely invisible →** keyboard shortcut (Win+S to search, Ctrl+L to focus URL bar, etc.). After the keypress, screenshot again before doing anything else.

This rule keeps you from reaching for the keyboard when the answer is already on the screen, and from typing raw coordinates when a known anchor mark + offset would do.

## Command Rules

- Treat command output as JSON, not prose.
- Use `--dry-run` before risky pointer or keyboard actions when planning a move.
- If a screenshot tool returns `vision_unavailable`, call `vision_init` and retry.
- Don't pre-emptively press Escape or click empty space to "clear state" — trust what the last screenshot shows.

## Common Commands

CLI form:

```sh
somatic doctor
somatic vision init
somatic vision status
somatic screenshot --annotate
somatic click <id>
somatic click <x,y>
somatic click-near <id> --dx 100 --dy 0
somatic type "text"
somatic hotkey ctrl s
somatic press enter
somatic scroll -4
somatic wait 1
somatic vision stop
```

MCP form (same names with underscores): `vision_init`, `screenshot_annotated`, `click`, `click_near`, `type_text`, `hotkey`, `press`, `scroll`, `wait`, `vision_stop`.

## Headless mode

If `headless_status` (or `somatic headless status`) reports `active: true`, you are operating against a virtual desktop spun up via Xvfb. **Everything in the operating loop above applies unchanged** — clicks and screenshots simply target the virtual display instead of the real one. You do not need to do anything different. To check whether your screenshots are coming from a real or virtual display, look at `headless_status` once at session start; that's it.

## Safety

SoMatic controls the real desktop session. Do not assume the active window is correct. Verify visible state with screenshots before typing, clicking destructive controls, submitting forms, deleting files, or changing system settings.
