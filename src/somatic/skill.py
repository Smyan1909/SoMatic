from __future__ import annotations

from importlib import resources


def skill_text() -> str:
    """Return the full SKILL.md operating loop shipped with the package."""
    return (resources.files("somatic") / "SKILL.md").read_text(encoding="utf-8")


def skill_summary() -> str:
    """Short, always-on hint surfaced as MCP server `instructions=`.

    Kept concise so MCP clients that include it in the system prompt don't pay
    a large token cost on every tool description load. Agents that need the
    full operating loop should call the `skill` MCP prompt or `somatic skill`.
    """
    return (
        "SoMatic is a Set-of-Marks UI automation surface. Workflow: vision_init "
        "→ screenshot_annotated → look at the inline image → act by mark id "
        "(click) or by id+offset (click_near) when YOLO missed the target; raw "
        "click(x,y) is the last resort. Re-screenshot after every consequential "
        "action. Call vision_stop when done. Use the `skill` prompt for the full "
        "operating loop."
    )
