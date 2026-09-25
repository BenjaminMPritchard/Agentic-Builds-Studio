from ._common import quoted_list, limit_words, numbers_in_input

NAME, VERSION, MAX_INPUT_CHARS = "summarise-comment", 1, 24000
SCHEMA = {"type": "object", "required": ["summary", "decisions", "open_questions"], "properties": {
    "summary": {"type": "string"},
    "decisions": {"type": "array", "maxItems": 8, "items": {"type": "string"}},
    "open_questions": {"type": "array", "maxItems": 8, "items": {"type": "string"}}}}
SYSTEM = ("Summarise the comment in at most 80 words. List decisions made and questions still open. "
          "Use only facts in the text. Never add numbers, names or links that are not in the text.")


def check(inp, out):
    return limit_words(out["summary"], 80) + numbers_in_input(inp, out["summary"], "summary")
