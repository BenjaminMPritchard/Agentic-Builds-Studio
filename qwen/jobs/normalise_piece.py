from ._common import text_of, numbers_in_input
import re

NAME, VERSION, MAX_INPUT_CHARS = "normalise-piece", 1, 8000
SCHEMA = {"type": "object", "required": ["name", "price_pence", "length_cm", "width_cm", "height_cm", "notes"],
          "properties": {"name": {"type": "string"}, "price_pence": {"type": "integer", "minimum": 0},
                         "length_cm": {"type": "integer", "minimum": 0}, "width_cm": {"type": "integer", "minimum": 0},
                         "height_cm": {"type": "integer", "minimum": 0}, "notes": {"type": "string"}}}
SYSTEM = ("Turn a free-text furniture listing into fields. Price in whole pence (GBP 45 = 4500). "
          "Dimensions in whole centimetres (convert from inches or metres). Use 0 for any missing value; never guess.")


def check(inp, out):
    hay = text_of(inp)
    errs = numbers_in_input(inp, out["notes"] + out["name"])
    pounds = {p.replace(",", "") for p in re.findall(r"£\s?(\d[\d,]*(?:\.\d+)?)", hay)}
    if out["price_pence"] and pounds and not any(round(float(p) * 100) == out["price_pence"] for p in pounds):
        errs.append("price_pence does not match a price in the input")
    if out["price_pence"] and not pounds:
        errs.append("price given but no price in input")
    return errs
