from ._common import limit_words

NAME, VERSION, MAX_INPUT_CHARS = "changelog-digest", 1, 24000
SCHEMA = {"type": "object", "required": ["digest"], "properties": {"digest": {"type": "string"}}}
SYSTEM = "Summarise these merged changes in plain English for a shop owner, at most 100 words."


def check(inp, out):
    return limit_words(out["digest"], 100)
