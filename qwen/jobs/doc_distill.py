from ._common import limit_words, numbers_in_input

NAME, VERSION, MAX_INPUT_CHARS = "doc-distill", 1, 30000
SCHEMA = {"type": "object", "required": ["distilled", "rules"], "properties": {
    "distilled": {"type": "string"}, "rules": {"type": "array", "maxItems": 15, "items": {"type": "string"}}}}
SYSTEM = "Distil the document: at most 150 words, plus up to 15 short rules it states. Do not add anything not in it."


def check(inp, out):
    return limit_words(out["distilled"], 150) + numbers_in_input(inp, out["distilled"], "distilled")
