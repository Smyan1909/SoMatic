"""Prompts used by the three benchmark agents.

These are deliberately spare and deterministic. We ask for JSON-only output
so the runner can parse without regex; `temperature=0.0` is set on the OpenAI
client so the same prompt + image yields the same answer across reruns.
"""

MARKS_PROMPT = """\
You are shown a screenshot with numbered red boxes drawn over UI elements
detected by a separate vision model. Each box has an integer id.

Your task: identify which numbered box best matches the following instruction.
Respond ONLY with a JSON object: {{"mark_id": <int>}}.

If no numbered box matches, respond {{"mark_id": null}}. Do not invent ids
that aren't in the list below.

Available marks (id -> bbox in pixels [x1, y1, x2, y2], confidence):
{marks}

Instruction:
{instruction}
"""


COORDS_PROMPT = """\
You are shown a screenshot of a desktop or web UI.

Your task: identify the (x, y) pixel coordinate that best satisfies the
following instruction. Respond ONLY with a JSON object: {{"x": <int>, "y": <int>}}.

Coordinates are in the original image's pixel space (0,0 is the top-left).
If the target is genuinely not present, respond {{"x": null, "y": null}}.

Instruction:
{instruction}
"""


COORDS_WITH_HINTS_PROMPT = """\
You are shown a screenshot of a desktop or web UI. A separate vision model has
detected the following UI elements (bounding boxes in pixels). Use them as
hints, but YOU must return the final (x, y) pixel coordinate yourself.

Detected elements (id -> bbox in pixels [x1, y1, x2, y2], confidence):
{marks}

Respond ONLY with a JSON object: {{"x": <int>, "y": <int>}} in original-image
pixel space (0,0 = top-left). If the target is genuinely not present, respond
{{"x": null, "y": null}}.

Instruction:
{instruction}
"""
