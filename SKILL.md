# SoMatic

Use SoMatic when you need to operate a native desktop UI with screenshots, mouse, and keyboard.

## How images reach you

**MCP path:** annotated screenshots arrive **inline** as image content in the tool response — you see the image directly, no extra step needed.

**CLI path:** `somatic screenshot --annotate --no-image` writes the annotated PNG to disk and returns its path in `screenshot.annotated_path`. Use the `Read` tool on that path to see the image. Do **not** try to parse the JSON output as an image — the bash tool returns text only.

## Operating Loop

1. **At the start of a session, run `vision_init` (MCP) or `somatic vision init` (CLI).** This loads the YOLO ONNX model into a background daemon. First-ever run may take 1–3 minutes; subsequent runs are near-instant. Require `"started": true` (or `"already_running": true`) before continuing.

2. **Always begin a task by taking an annotated screenshot and visually inspecting it.**
   - MCP: call `screenshot_annotated` — the image arrives inline.
   - CLI: run `somatic screenshot --annotate --no-image`, then `Read` the path at `screenshot.annotated_path`.

3. **Scan the image before acting.** Check every region — taskbar, dock, desktop icons, system tray, open windows — and identify which numbered mark corresponds to the element you want.

4. **Prefer clicks on visible elements over keyboard navigation.** If the target is already present in the annotated screenshot (a taskbar icon, a tab, a button, a link), click its mark id. Do **not** open Start menu / Run / search when the thing you want is already on screen.

5. **Use the keyboard for what keyboards are for, not as a shortcut around looking.** Keyboard is the right tool for:
   - typing free-form text (`type_text "hello"`)
   - key chords that aren't UI elements (`hotkey ctrl s`, `press enter`, `hotkey alt tab`)
   - launching something that genuinely isn't visible anywhere (then use Win+S, type, screenshot the results, click the best match by mark id — don't blind-press Enter)

6. Inspect the JSON returned by the screenshot tool: `marks` contains `id`, `bbox`, `center`, and `confidence`. There are no captions — refer to elements by id and verify visually.

7. Act by mark id whenever possible:
   - `click 4`
   - `move 7`
   - `scroll -5 --target 2`

8. When YOLO **doesn't** annotate the exact target — empty text inputs, fields that follow a labelled icon, gaps between buttons — use `click_near` with a `dx`/`dy` offset from the nearest visible mark:
   - `click_near 12 --dx 300 --dy 0` (300 px to the right of mark 12)

9. Use raw coordinates only as a last resort when no mark and no anchor exists:
   - `click 640,420`

10. **Re-screenshot after every consequential action.** Mark IDs are reassigned per screenshot — never apply an id from one screenshot to another screenshot's state.

11. **At the end of the session, run `vision_stop`** to free the model's memory.

12. If something goes wrong, run `doctor` and `vision_status`.

## Decision Rule: Click, Click-Near, or Type?

When choosing how to advance the task, ask: *what does the latest annotated screenshot show?*

- **Target visible as a mark →** `click <id>`. Don't open a launcher.
- **Target NOT visible as a mark but adjacent to one →** `click_near <id> --dx ... --dy ...`. (Common for text inputs that sit next to a `+` or send button.)
- **Target's container visible but not the target itself →** click into the container first, re-screenshot, then act on the new marks.
- **Target genuinely invisible →** keyboard shortcut (Win+S to search, Ctrl+L to focus URL bar, etc.). After the keypress, screenshot again before doing anything else.

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
somatic screenshot --annotate --no-image   # returns annotated_path; use Read to view
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

If `headless_status` (or `somatic headless status`) reports `active: true`, you are operating against a virtual desktop spun up via Xvfb. **Everything in the operating loop above applies unchanged** — clicks and screenshots simply target the virtual display instead of the real one.

## Safety

SoMatic controls the real desktop session. Do not assume the active window is correct. Verify visible state with screenshots before typing, clicking destructive controls, submitting forms, deleting files, or changing system settings.
