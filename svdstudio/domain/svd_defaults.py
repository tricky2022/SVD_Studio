"""CMSIS-SVD effective defaults applied when creating objects.

Reference: CMSIS-SVD schema. Optional elements have no value when omitted,
which means "inherit from parent" (field <- register <- peripheral <- device).
When the user creates a register/field in SVD Studio we materialize the
effective values so the object is valid and self-describing on its own:

- access: "read-write" (schema default for registers; fields inherit it)
- size: 32 (most common; dialog lets the user pick 8/16/32/64)
- reset_value: 0x0, reset_mask: full width mask
- protection/read_action/modified_write_values/write_constraint: "" (unset,
  meaning "no constraint / inherit"). These MUST stay empty unless the user
  explicitly sets them — writing a value changes SVD semantics.
"""
from __future__ import annotations

REGISTER_DEFAULTS = {
    "access": "read-write",
    "size": 32,
    "reset_value": 0x0,
    "reset_mask": 0xFFFFFFFF,
    "protection": "",
    "read_action": "",
    "modified_write_values": "",
    "write_constraint": "",
}

FIELD_DEFAULTS = {
    "access": "",  # empty = inherit from parent register
    "read_action": "",
    "modified_write_values": "",
    "write_constraint": "",
}


def new_register(name: str, address_offset: int = 0, **overrides):
    from svdstudio.domain.model import SvdRegister
    values = dict(REGISTER_DEFAULTS)
    values.update({k: v for k, v in overrides.items() if v != "" or k == "access"})
    values["name"] = name
    values["address_offset"] = address_offset
    if values.get("reset_mask") == "":
        values.pop("reset_mask", None)
    # full-width mask follows the chosen size
    size = values.get("size", 32)
    if "reset_mask" in values and isinstance(values["reset_mask"], int):
        values["reset_mask"] = (1 << size) - 1 if size < 64 else 0xFFFF_FFFF_FFFF_FFFF
    return SvdRegister(**{k: v for k, v in values.items()
                          if k in SvdRegister.__dataclass_fields__})


def new_field(name: str, bit_offset: int, bit_width: int,
              parent_access: str = "", **overrides):
    from svdstudio.domain.model import SvdField
    values = dict(FIELD_DEFAULTS)
    values["access"] = overrides.get("access", "") or parent_access or ""
    for key in ("read_action", "modified_write_values", "write_constraint", "description"):
        if overrides.get(key, "") != "":
            values[key] = overrides[key]
    return SvdField(name=name, bit_offset=bit_offset, bit_width=bit_width,
                    lsb=bit_offset, msb=bit_offset + bit_width - 1, **values)
