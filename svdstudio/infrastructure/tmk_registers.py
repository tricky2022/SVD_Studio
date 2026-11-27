"""Bridge between native core-register groups and TMKStudioIDE profile XML."""
from __future__ import annotations

from pathlib import Path
from typing import BinaryIO
from zipfile import BadZipFile, ZipFile

from lxml import etree

from svdstudio.domain.model import CoreRegister, CoreRegisterGroup, SvdField

_PROFILE_ENTRIES = (
    "cn/com/tmkstudio/debug/registers/c28xx.xml",
    "cn/com/tmkstudio/debug/registers/c28xx-fpu.xml",
)
_ACCESS_CODES = {"", "R", "W", "RW", "N"}
_CMSIS_ACCESS_CODES = {"read-only": "R", "write-only": "W", "read-write": "RW"}


def load_tmk_register_profile(path: str | Path) -> CoreRegisterGroup:
    """Read a standalone TMK CPU or FPU register profile."""
    with Path(path).open("rb") as stream:
        return _parse_profile(stream, str(path))


def load_tmk_register_profiles_from_jar(path: str | Path) -> list[CoreRegisterGroup]:
    """Read the CPU and simulator FPU profiles from a TMK debug core plugin JAR."""
    try:
        with ZipFile(path) as archive:
            groups = []
            for entry in _PROFILE_ENTRIES:
                with archive.open(entry) as stream:
                    groups.append(_parse_profile(stream, entry))
            return groups
    except BadZipFile as error:
        raise ValueError(f"Invalid TMK debug core plugin archive {path}") from error
    except KeyError as error:
        raise ValueError(f"TMK profile is missing from {path}: {error.args[0]}") from error


def _parse_profile(stream: BinaryIO, source: str) -> CoreRegisterGroup:
    parser = etree.XMLParser(no_network=True, resolve_entities=False, remove_comments=True)
    try:
        document = etree.parse(stream, parser)
        if document.docinfo.doctype:
            raise ValueError("DOCTYPE declarations are unsupported in TMK profiles")
        root = document.getroot()
        _check_element(root, "cpu", {"id", "description"})
        group = CoreRegisterGroup(name=_name(root), description=root.get("description", ""))
        register_names: set[str] = set()
        for entry in root:
            _check_element(entry, "register", {"id", "width", "description"})
            register = CoreRegister(
                name=_name(entry),
                size=_decimal(entry, "width"),
                description=entry.get("description", ""),
            )
            _check_unique(register_names, register.name)
            _check_size(register.size, register.name)
            field_names: set[str] = set()
            for field in entry:
                register.fields.append(_parse_field(field, register, field_names))
            group.registers.append(register)
        return group
    except (etree.XMLSyntaxError, ValueError) as error:
        raise ValueError(f"{source}: {error}") from error


def _parse_field(element, register: CoreRegister, names: set[str]) -> SvdField:
    _check_element(element, "bitfield", {"id", "begin", "end", "description", "access"})
    if len(element):
        raise ValueError(f"Unexpected child element of <bitfield> at line {element.sourceline}")
    name = _name(element)
    _check_unique(names, name)
    high = _decimal(element, "begin")
    low = _decimal(element, "end")
    _check_range(register, name, low, high)
    access = element.get("access", "").strip()
    if access.upper() not in _ACCESS_CODES:
        raise ValueError(f"{register.name}.{name} has unsupported access code {access!r}")
    return SvdField(
        name=name,
        description=element.get("description", ""),
        bit_offset=low,
        bit_width=high - low + 1,
        lsb=low,
        msb=high,
        access=access,
    )


def _check_element(element, tag: str, allowed_attributes: set[str]) -> None:
    if element.tag != tag:
        actual = element.tag if isinstance(element.tag, str) else "XML node"
        raise ValueError(f"Expected <{tag}>, got {actual} at line {element.sourceline}")
    unknown = set(element.attrib) - allowed_attributes
    if unknown:
        attributes = ", ".join(sorted(unknown))
        raise ValueError(f"Unsupported attributes on <{tag}> at line {element.sourceline}: {attributes}")
    if (element.text or "").strip() or (element.tail or "").strip():
        raise ValueError(f"Unexpected text at line {element.sourceline}")


def _name(element) -> str:
    name = element.get("id", "").strip()
    if not name:
        raise ValueError(f"Missing id on <{element.tag}> at line {element.sourceline}")
    return name


def _decimal(element, attribute: str) -> int:
    value = element.get(attribute, "").strip()
    if not value.isascii() or not value.isdecimal():
        raise ValueError(f"{attribute} on <{element.tag}> must be decimal at line {element.sourceline}")
    return int(value)


def _check_unique(names: set[str], name: str) -> None:
    if name.upper() in names:
        raise ValueError(f"Duplicate identifier {name!r} in TMK profile")
    names.add(name.upper())


def _check_size(size: int, name: str) -> None:
    if not 1 <= size <= 64:
        raise ValueError(f"{name!r} width must be between 1 and 64 bits")


def _check_range(register: CoreRegister, name: str, low: int, high: int) -> None:
    if not 0 <= low <= high < register.size:
        raise ValueError(f"{register.name}.{name} bit range exceeds its {register.size}-bit register")


def _attributes(name: str, description: str) -> dict[str, str]:
    name = name.strip()
    if not name:
        raise ValueError("TMK profile identifiers must be nonempty")
    attributes = {"id": name}
    if description:
        attributes["description"] = description
    return attributes


def save_tmk_register_profile(group: CoreRegisterGroup, path: str | Path) -> None:
    """Export a core-register group as a legacy TMK CPU or FPU XML profile."""
    root = etree.Element("cpu", **_attributes(group.name, group.description))
    register_names: set[str] = set()
    for register in group.registers:
        attributes = _attributes(register.name, register.description)
        _check_unique(register_names, attributes["id"])
        _check_size(register.size, register.name)
        if register.access or register.reset_value is not None or register.reset_mask is not None:
            raise ValueError(f"TMK XML cannot represent register access or reset metadata for {register.name}")
        entry = etree.SubElement(root, "register", **attributes, width=str(register.size))
        field_names: set[str] = set()
        for field in register.fields:
            _write_field(entry, register, field, field_names)

    data = etree.tostring(root, encoding="UTF-8", xml_declaration=True, pretty_print=True)
    Path(path).write_bytes(data)


def _write_field(entry, register: CoreRegister, field: SvdField, names: set[str]) -> None:
    attributes = _attributes(field.name, field.description)
    _check_unique(names, attributes["id"])
    low = field.bit_offset
    high = low + field.bit_width - 1
    _check_range(register, field.name, low, high)
    if (
        field.reset_value is not None
        or field.read_action
        or field.modified_write_values
        or field.write_constraint
        or field.write_constraint_min is not None
        or field.write_constraint_max is not None
        or field.enumerated_values
        or field.derived_from
        or field.dim.dim
    ):
        raise ValueError(f"TMK XML cannot represent extra field metadata for {register.name}.{field.name}")
    access = _CMSIS_ACCESS_CODES.get(field.access, field.access)
    if access.upper() not in _ACCESS_CODES:
        raise ValueError(f"{register.name}.{field.name} has unsupported access code {field.access!r}")
    if access:
        attributes["access"] = access
    etree.SubElement(entry, "bitfield", **attributes, begin=str(high), end=str(low))
