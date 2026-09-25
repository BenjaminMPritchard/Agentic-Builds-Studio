from ._common import quotes_in_input

NAME, VERSION, MAX_INPUT_CHARS = "extract-lessons", 1, 24000
SCHEMA = {"type": "object", "required": ["lessons"], "properties": {"lessons": {
    "type": "array", "maxItems": 10, "items": {"type": "object", "required": ["lesson", "evidence"],
    "properties": {"lesson": {"type": "string"}, "evidence": {"type": "string"}}}}}}
SYSTEM = ("From hand-off process notes and comments, extract reusable lessons about how the work went "
          "(what slowed us down, what worked). `evidence` is the exact sentence. No personal data.")


def check(inp, out):
    return quotes_in_input(inp, [l["evidence"] for l in out["lessons"]], "evidence")
