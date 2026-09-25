from ._common import quotes_in_input

NAME, VERSION, MAX_INPUT_CHARS = "extract-questionnaire", 1, 24000
SCHEMA = {"type": "object", "required": ["questions"], "properties": {"questions": {
    "type": "array", "maxItems": 40, "items": {"type": "object", "required": ["question", "quote"],
    "properties": {"question": {"type": "string"}, "quote": {"type": "string"}}}}}}
SYSTEM = "Extract every question put to the client, with the exact source sentence as `quote`."


def check(inp, out):
    return quotes_in_input(inp, [q["quote"] for q in out["questions"]])
