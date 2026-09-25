"""Tiny JSON-schema subset validator: type, enum, required, properties, items, minimum."""

TYPES = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float),
         "boolean": bool, "null": type(None)}


def validate(value, schema, path="$"):
    errs = []
    t = schema.get("type")
    if t:
        ok = isinstance(value, TYPES[t]) and not (t in ("integer", "number") and isinstance(value, bool))
        if not ok:
            return [f"{path}: expected {t}"]
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: {value!r} not in {schema['enum']}")
    if "minimum" in schema and isinstance(value, (int, float)) and value < schema["minimum"]:
        errs.append(f"{path}: below minimum")
    if t == "object":
        for k in schema.get("required", []):
            if k not in value:
                errs.append(f"{path}.{k}: missing")
        for k, sub in schema.get("properties", {}).items():
            if k in value:
                errs += validate(value[k], sub, f"{path}.{k}")
    if t == "array":
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errs.append(f"{path}: too many items")
        for i, v in enumerate(value):
            errs += validate(v, schema.get("items", {}), f"{path}[{i}]")
    return errs
