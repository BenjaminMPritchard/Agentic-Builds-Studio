NAME, VERSION, MAX_INPUT_CHARS = "mechanical-edit", 1, 8000
SCHEMA = {"type": "object", "required": ["edited"], "properties": {"edited": {"type": "string"}}}
SYSTEM = "Apply the instruction to the text and return the whole edited text."


def check(inp, out):
    # Off until 8 of 10 golden edits pass. A pure edit must not change length wildly.
    src = inp.get("text", "")
    return [] if src and 0.5 <= len(out["edited"]) / len(src) <= 2 else ["edit changed the text size too much"]
