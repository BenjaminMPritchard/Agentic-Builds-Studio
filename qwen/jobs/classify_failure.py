from ._common import quotes_in_input

NAME, VERSION, MAX_INPUT_CHARS = "classify-failure", 1, 24000
CATS = ["lint", "types", "test-failure", "migration", "dependency", "flaky", "infrastructure", "unknown"]
SCHEMA = {"type": "object", "required": ["category", "evidence"], "properties": {
    "category": {"type": "string", "enum": CATS}, "evidence": {"type": "string"}}}
SYSTEM = ("Classify why this CI or test log failed. `category` is one of: " + ", ".join(CATS) +
          ". `evidence` is the exact log line that shows it. If unsure use 'unknown'.")


def check(inp, out):
    return quotes_in_input(inp, [out["evidence"]], "evidence")
