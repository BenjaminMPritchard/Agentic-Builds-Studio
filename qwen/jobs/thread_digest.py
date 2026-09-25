from ._common import limit_words, numbers_in_input

NAME, VERSION, MAX_INPUT_CHARS = "thread-digest", 1, 30000
SCHEMA = {"type": "object", "required": ["digest", "waiting_on"], "properties": {
    "digest": {"type": "string"}, "waiting_on": {"type": "string"}}}
SYSTEM = "Digest this thread in at most 120 words. `waiting_on` is who must act next (a role or 'nobody'). Facts only."


def check(inp, out):
    return limit_words(out["digest"], 120) + numbers_in_input(inp, out["digest"], "digest")
