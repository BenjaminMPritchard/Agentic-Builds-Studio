from ._common import quotes_in_input

NAME, VERSION, MAX_INPUT_CHARS = "todo-owner-questions", 1, 24000
SCHEMA = {"type": "object", "required": ["items"], "properties": {"items": {
    "type": "array", "maxItems": 40, "items": {"type": "object", "required": ["question", "quote"],
    "properties": {"question": {"type": "string"}, "quote": {"type": "string"}}}}}}
SYSTEM = ("Find every place marked TODO(owner) or otherwise waiting on the owner's answer. "
          "`question` is what needs asking; `quote` is the exact line.")


def check(inp, out):
    return quotes_in_input(inp, [i["quote"] for i in out["items"]])
