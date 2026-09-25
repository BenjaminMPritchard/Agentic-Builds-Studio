from ._common import quoted_list, quotes_in_input

NAME, VERSION, MAX_INPUT_CHARS = "extract-followups", 1, 24000
SCHEMA = quoted_list("followups", "title", "quote")
SYSTEM = ("List follow-up work the text says should be done later (TODOs, 'next time', deferred items). "
          "For each give a short title and the exact sentence from the text as `quote`. Return an empty list if none.")


def check(inp, out):
    return quotes_in_input(inp, [f["quote"] for f in out["followups"]])
