# SoMatic as an MCP Server

SoMatic ships an MCP (Model Context Protocol) server so Claude Code, Cursor, Continue, and any other MCP-capable agent can see annotated screenshots **inline** — no separate `Read` tool call required.

## Add to Claude Code

### Via npm (recommended)

```sh
claude mcp add somatic -- npx -y @somatic-cli/cli mcp serve
```

Or add directly to your workspace `.mcp.json`:

```json
{
  "mcpServers": {
    "somatic": {
      "command": "npx",
      "args": ["-y", "@somatic-cli/cli", "mcp", "serve"]
    }
  }
}
```

> **Note:** `npx` runs the Node shim, which requires Python 3.10+ on `PATH` with `somatic-cli[vision,mcp]` installed. Run `pip install 'somatic-cli[vision,mcp]'` once before using this path.

### Via pip (Python-only installs)

```sh
claude mcp add somatic -- python -m somatic.mcp_server
```

Or in `.mcp.json`:

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

A `somatic-mcp` entry point is also installed, so `"command": "somatic-mcp"` works equivalently.

## Load the operating loop

Invoke the `skill` prompt once per session to load the full operating loop into context:

```
use the skill prompt
```

The skill content is also in [`SKILL.md`](../SKILL.md) at the repo root for easy reference.

## Operating Loop (when running under MCP)

1. Load the operating-loop context — invoke the `skill` prompt once per session.
2. `vision_init` — loads the YOLO ONNX model (first run downloads weights; later runs are near-instant).
3. `screenshot_annotated` — returns the annotated PNG inline (you see it directly) plus the marks JSON.
4. Act by mark id with `click <id>`; when YOLO missed the target use `click_near <id> dx dy`; raw `click "x,y"` is the last resort.
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
| `skill` | text | The full SoMatic operating loop (mirrors [`SKILL.md`](../SKILL.md)) |

## Notes & gotchas

- **Daemon lifetime is independent of the MCP client.** The vision daemon runs as a separate background process. Closing Claude Code does not stop it; call `vision_stop` explicitly or kill it manually.
- **The image arrives in the model's context.** Claude Code's UI currently renders MCP image content in a collapsed accordion rather than inline in the chat. The model still sees and reasons about the image.
- **Stdout is the MCP transport.** Do not run the CLI's other commands through the same Python process while the MCP server is running — anything written to stdout corrupts the protocol stream.

## Non-MCP harnesses

If your agent runtime can't speak MCP, the plain CLI is the fallback. `somatic screenshot --annotate` returns `image_b64` and `annotated_image_b64` directly in its JSON output. Use `--no-image` to opt out for low-bandwidth pipelines.
