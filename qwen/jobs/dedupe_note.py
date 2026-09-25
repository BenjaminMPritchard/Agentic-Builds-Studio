NAME, VERSION, MAX_INPUT_CHARS = "dedupe-note", 1, 12000
SCHEMA = {"type": "object", "required": ["duplicate_of"], "properties": {
    "duplicate_of": {"type": "integer", "minimum": -1}}}
SYSTEM = ("`input.new` is a note; `input.existing` is a list of notes. Return the index of an existing note "
          "that says the same thing, or -1 if none does.")


def check(inp, out):
    n = len(inp.get("existing", []))
    return [] if out["duplicate_of"] < n else [f"index {out['duplicate_of']} out of range"]
