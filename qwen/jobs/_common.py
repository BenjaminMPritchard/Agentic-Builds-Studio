"""Shared pieces for Worker jobs. A job module defines:

NAME, VERSION, MAX_INPUT_CHARS, SCHEMA, SYSTEM (prompt), and check(inp, out) -> list of error strings.
`inp` is the job document's `input` (a dict). No check, no Qwen.
"""
import re


def text_of(inp):
    """All the text in the input, for 'does this quote/number appear' checks."""
    if isinstance(inp, str):
        return inp
    if isinstance(inp, dict):
        return "\n".join(text_of(v) for v in inp.values())
    if isinstance(inp, list):
        return "\n".join(text_of(v) for v in inp)
    return str(inp)


def norm(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def quotes_in_input(inp, quotes, label="quote"):
    hay = norm(text_of(inp))
    return [f"{label} not found in input: {q[:60]!r}" for q in quotes if norm(q) not in hay]


def numbers_in_input(inp, text_out, label="output"):
    """Every number written in the output must appear in the input."""
    hay = text_of(inp)
    have = set(re.findall(r"\d+(?:[.,]\d+)?", hay))
    return [f"number {n} in {label} not in input" for n in re.findall(r"\d+(?:[.,]\d+)?", text_out) if n not in have]


def limit_words(s, n):
    return [] if len(s.split()) <= n else [f"too long ({len(s.split())} words, max {n})"]


def strs(*names, **kw):
    return {"type": "object", "required": list(names),
            "properties": {n: {"type": "string"} for n in names}, **kw}


def quoted_list(key, *fields, max_items=20):
    props = {f: {"type": "string"} for f in fields}
    return {"type": "object", "required": [key], "properties": {
        key: {"type": "array", "maxItems": max_items,
              "items": {"type": "object", "required": list(fields), "properties": props}}}}
