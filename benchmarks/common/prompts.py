"""Prompts used by the three benchmark agents.

These are deliberately spare and deterministic. We ask for JSON-only output
so the runner can parse without regex; `temperature=0.0` is set on the OpenAI
client so the same prompt + image yields the same answer across reruns.
"""

MARKS_PROMPT = """\
You are shown a screenshot annotated with numbered red boxes drawn over UI
elements detected by a separate vision model. Each box has an integer id.

Your task: identify the click location that best satisfies the instruction.
You have THREE possible actions, in order of preference:

1. CLICK a numbered box, when that box exactly contains the target element:
       {{"action": "click", "mark_id": <int>}}

2. CLICK_NEAR a numbered box, when a box is adjacent to the target but doesn't
   exactly contain it (e.g. the target is right next to or directly above/below
   a detected element). dx is positive to the right, dy is positive downward,
   both in original-image pixels. The final click is at (mark.center.x + dx,
   mark.center.y + dy):
       {{"action": "click_near", "mark_id": <int>, "dx": <int>, "dy": <int>}}

3. CLICK_XY at raw coordinates, when no nearby box helps (the vision model
   missed this region entirely). Coordinates are in the original image's pixel
   space; (0, 0) is the top-left:
       {{"action": "click_xy", "x": <int>, "y": <int>}}

If the target is genuinely not present, respond {{"action": "refuse"}}.

Prefer (1) when possible; fall back to (2) for offsets within ~200 px of a
detected mark; use (3) only when YOLO clearly missed the region. Do NOT
invent mark ids that aren't in the list below.

Image dimensions: {width} x {height} pixels.

Available marks (id -> bbox [x1, y1, x2, y2], confidence):
{marks}

Instruction:
{instruction}

Respond with ONLY one of the four JSON objects above. No prose.
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
