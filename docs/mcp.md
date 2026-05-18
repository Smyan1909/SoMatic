# SoMatic as an MCP Server

SoMatic ships an MCP (Model Context Protocol) server so Claude Code, Cursor, Continue, and any other MCP-capable agent can see annotated screenshots **inline** — no separate `Read` tool call required. This is the "agent-browser-style" path; the plain CLI is the fallback.

## Install

```sh
pip install -e .[vision,mcp]
```

The `[mcp]` extra pulls in the official MCP Python SDK (which includes FastMCP). The `[vision]` extra is still required because the MCP server delegates inference to the existing vision daemon.

## Wire into Claude Code

CLI form:

```sh
claude mcp add somatic -- python -m somatic.mcp_server
```

…or add to your workspace `.mcp.json`:

```json
{
  "mcpServers": {
    "somatic": {
      "command": "python",
      "args": ["-m", "somatic.mcp_server"]
    }
  }
}
```

A `somatic-mcp` console entry point is also installed, so `command: "somatic-mcp"` works equivalently.

## Operating Loop (when running under MCP)

1. Load the operating-loop context — invoke the `skill` prompt once per session.
2. `vision_init` — loads the YOLO ONNX model (first run does the `.pt → .onnx` conversion; later runs are near-instant).
3. `screenshot_annotated` — returns the annotated PNG inline (you see it directly) plus the marks JSON.
4. Act by mark id with `click <id>`; when YOLO missed the target (typical for empty text inputs), use `click_near <id> dx dy`; raw `click "x,y"` is the last resort.
5. `vision_stop` at the end to free model memory.

## Tools

| Tool | Returns | Notes |
|---|---|---|
| `vision_init` | text | Start the daemon; idempotent |
| `vision_stop` | text | Stop the daemon and free memory |
| `vision_status` | text | Health check |
| `screenshot_annotated` | **image + text** | Annotated PNG inline + marks JSON |
| `screenshot` | **image + text** | Raw capture inline + dimensions |
| `click` | text | Mark id (`"5"`) or coordinate (`"640,420"`) |
| `click_near` | text | Mark id + `dx` / `dy` offset |
| `move`, `scroll` | text | Pointer movement / scroll |
| `type_text`, `hotkey`, `press` | text | Keyboard actions |
| `wait` | text | Sleep between actions |

## Prompts

| Prompt | Returns | Notes |
|---|---|---|
| `skill` | text | The full SoMatic operating loop (mirror of SKILL.md) |

## Notes & gotchas

- **Daemon lifetime is independent of the MCP client.** The vision daemon runs as a separate background process (it must, because the model has to stay loaded across tool calls). Closing Claude Code does not stop it; call `vision_stop` explicitly or `taskkill` / `kill` it manually.
- **The image arrives in the model's context.** Claude Code's UI currently renders MCP image content in a collapsed accordion rather than inline in the chat (open issue upstream). The model still sees and reasons about the image — that's the part that matters for agent workflows.
- **Stdout is the MCP transport.** Do not run the CLI's other commands through the same Python process while the MCP server is running — anything written to stdout corrupts the protocol stream.

## Non-MCP harnesses

If your agent runtime can't speak MCP, the plain CLI is the fallback. `somatic screenshot --annotate` now returns `image_b64` and `annotated_image_b64` directly in its JSON output, base64-encoded PNGs that you can feed to the model as image content in the same call. Use `--no-image` to opt out for low-bandwidth pipelines (tests, scripts).
