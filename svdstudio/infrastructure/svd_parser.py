"""SVD XML -> domain parser (infrastructure, lxml allowed here)."""
from __future__ import annotations

import re

from lxml import etree

from svdstudio.domain.model import *


def _t(node, tag, default=""):
    el = node.find(tag)
    return el.text.strip() if el is not None and el.text else default

def _i(node, tag, default=0):
    txt = _t(node, tag, "")
    if not txt: return default
    try: return int(txt, 0)
    except ValueError: return default

def _parse_dim(node) -> DimInfo:
    d = DimInfo()
    dim = node.find("dim")
    if dim is not None and dim.text:
        d.dim = int(dim.text.strip(), 0)
        d.dim_increment = _i(node, "dimIncrement", 0)
        di = _t(node, "dimIndex", "")
        if di: d.dim_index = [x.strip() for x in di.split(",")]
    return d

def _parse_enum_values(node) -> EnumeratedValues:
    ev = EnumeratedValues(name=_t(node, "name"), usage=_t(node, "usage"),
                          header_enum_name=_t(node, "headerEnumName"))
    ev.derived_from = node.get("derivedFrom", "")
    for e in node.findall("enumeratedValue"):
        v = _t(e, "value", "0")
        try: iv = int(v, 0)
        except ValueError: iv = 0
        desc = _t(e, "description")
        is_default = _t(e, "isDefault") == "true"
        item = EnumValue(name=_t(e, "name"), description=desc, value=iv,
                         is_default=is_default)
        _mark_line(e, item)
        ev.values.append(item)
    return ev


def _parse_write_constraint(node) -> tuple[str, int | None, int | None]:
    """Normalize a <writeConstraint> element to (kind, minimum, maximum).

    CMSIS-SVD models this as a choice of child elements:
        <writeAsRead>true</writeAsRead>
        <useEnumeratedValues>true</useEnumeratedValues>
        <range><minimum>N</minimum><maximum>M</maximum></range>
    Anything else (vendor text) is preserved verbatim as the kind so no
    information is silently dropped.
    """
    rg = node.find("range")
    if rg is not None:
        mn, mx = rg.find("minimum"), rg.find("maximum")
        minimum = int(mn.text.strip(), 0) if mn is not None and mn.text else None
        maximum = int(mx.text.strip(), 0) if mx is not None and mx.text else None
        return "range", minimum, maximum
    if node.find("writeAsRead") is not None:
        return "writeAsRead", None, None
    if node.find("useEnumeratedValues") is not None:
        return "useEnumeratedValues", None, None
    return "".join(node.itertext()).strip(), None, None


def _parse_field(n) -> SvdField:
    wc_el = n.find("writeConstraint")
    constr, wc_min, wc_max = _parse_write_constraint(wc_el) if wc_el is not None else ("", None, None)
    f = SvdField(name=_t(n, "name"), description=_t(n, "description"),
                 access=_t(n, "access"), read_action=_t(n, "readAction"),
                 modified_write_values=_t(n, "modifiedWriteValues"),
                 write_constraint=constr,
                 write_constraint_min=wc_min, write_constraint_max=wc_max)
    _mark_line(n, f)
    f.derived_from = n.get("derivedFrom", "")
    f.dim = _parse_dim(n)
    bo = n.find("bitOffset"); bw = n.find("bitWidth")
    lsb = n.find("lsb"); msb = n.find("msb"); br = n.find("bitRange")
    if bo is not None and bw is not None:
        f.source_range_form = "bitOffset"
        f.bit_offset = int(bo.text.strip(), 0); f.bit_width = int(bw.text.strip(), 0)
        f.lsb = f.bit_offset; f.msb = f.bit_offset + f.bit_width - 1
    elif lsb is not None and msb is not None:
        f.source_range_form = "lsb_msb"
        f.lsb = int(lsb.text.strip(), 0); f.msb = int(msb.text.strip(), 0)
        f.bit_offset = f.lsb; f.bit_width = f.msb - f.lsb + 1
    elif br is not None and br.text:
        import re
        m = re.match(r"\[(\d+):(\d+)\]", br.text.strip())
        if m:
            f.source_range_form = "bitRange"
            f.msb = int(m.group(1)); f.lsb = int(m.group(2))
            f.bit_offset = f.lsb; f.bit_width = f.msb - f.lsb + 1
    if n.find("resetValue") is not None: f.reset_value = _i(n, "resetValue")
    for evn in n.findall("enumeratedValues"):
        f.enumerated_values.append(_parse_enum_values(evn))
    return f

def _parse_register(n) -> SvdRegister:
    wc_el = n.find("writeConstraint")
    constr, wc_min, wc_max = _parse_write_constraint(wc_el) if wc_el is not None else ("", None, None)
    r = SvdRegister(name=_t(n, "name"), display_name=_t(n, "displayName"),
                    description=_t(n, "description"), access=_t(n, "access"),
                    protection=_t(n, "protection"), read_action=_t(n, "readAction"),
                    modified_write_values=_t(n, "modifiedWriteValues"),
                    write_constraint=constr,
                    write_constraint_min=wc_min, write_constraint_max=wc_max)
    r.address_offset = _i(n, "addressOffset")
    size_el = n.find("size")
    r.size = _i(n, "size") if size_el is not None else None
    reset_el = n.find("resetValue")
    r.reset_value = _i(n, "resetValue") if reset_el is not None else None
    mask_el = n.find("resetMask")
    r.reset_mask = _i(n, "resetMask") if mask_el is not None else None
    _mark(n, r, "size", "resetValue", "resetMask", "access", "protection",
           "readAction", "modifiedWriteValues", "writeConstraint")
    r.derived_from = n.get("derivedFrom", "")
    r.alternate_register = _t(n, "alternateRegister")
    r.dim = _parse_dim(n)
    _mark_line(n, r)
    for fn in n.findall("fields/field"):
        r.fields.append(_parse_field(fn))
    for evn in n.findall("enumeratedValues"):
        r.enumerated_values.append(_parse_enum_values(evn))
    return r

def _parse_cluster(n) -> SvdCluster:
    c = SvdCluster(name=_t(n, "name"), description=_t(n, "description"))
    c.address_offset = _i(n, "addressOffset")
    c.derived_from = n.get("derivedFrom", "")
    c.dim = _parse_dim(n)
    for rn in n.findall("register"):
        c.registers.append(_parse_register(rn))
    for cn in n.findall("cluster"):
        c.clusters.append(_parse_cluster(cn))
    return c

def _parse_interrupt(n) -> SvdInterrupt:
    interrupt = SvdInterrupt(name=_t(n, "name"),
                             description=_t(n, "description"),
                             value=_i(n, "value", 0))
    _mark_line(n, interrupt)
    _mark(n, interrupt, "name", "description", "value")
    return interrupt


def _parse_peripheral(n) -> SvdPeripheral:
    p = SvdPeripheral(name=_t(n, "name"), display_name=_t(n, "displayName"),
                      description=_t(n, "description"), group_name=_t(n, "groupName"),
                      prepend_to_name=_t(n, "prependToName"), append_to_name=_t(n, "appendToName"),
                      header_struct_name=_t(n, "headerStructName"),
                      disable_condition=_t(n, "disableCondition"))
    p.base_address = _i(n, "baseAddress")
    p.derived_from = n.get("derivedFrom", "")
    p.dim = _parse_dim(n)
    _mark_line(n, p)
    for ab in n.findall("addressBlock"):
        p.address_blocks.append(AddressBlock(offset=_i(ab, "offset"), size=_i(ab, "size"), usage=_t(ab, "usage", "registers")))
    for int_el in n.findall("interrupt"):
        p.interrupts.append(_parse_interrupt(int_el))
    regs = n.find("registers")
    if regs is not None:
        for rn in regs.findall("register"): p.registers.append(_parse_register(rn))
        for cn in regs.findall("cluster"): p.clusters.append(_parse_cluster(cn))
    return p

# Defensive limits: a hostile or broken vendor file must fail fast with a
# clear message instead of freezing the workbench.
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_REGISTERS = 50000
MAX_FIELDS = 300000


def parse_error_position(error: Exception) -> tuple[int, int]:
    """Extract (line, column) from an lxml error, or (0, 0) when unknown."""
    position = getattr(error, "position", None)
    if isinstance(position, tuple) and len(position) == 2:
        return int(position[0]), int(position[1])
    lineno = getattr(error, "lineno", None)
    offset = getattr(error, "offset", None)
    if lineno:
        return int(lineno), int(offset or 0)
    # lxml sometimes only embeds the position in the message text
    match = re.search(r"line (\d+), column (\d+)", str(error))
    if match:
        return int(match.group(1)), int(match.group(2))
    match = re.search(r"line (\d+)", str(error))
    if match:
        return int(match.group(1)), 0
    return 0, 0


def _mark_line(element, obj) -> None:
    """Record the source line of an element on its domain object."""
    line = getattr(element, "sourceline", None)
    if line and getattr(obj, "meta", None) is not None:
        obj.meta.line = int(line)


def _mark(element, obj, *attrs: str) -> None:
    """Record which child elements were present in the source scalar form."""
    meta = getattr(obj, "meta", None)
    if meta is None:
        return
    if element is None:
        return
    for tag in attrs:
        if element.find(tag) is not None:
            meta.present.add(tag)


def _count(root, tags: tuple[str, ...]) -> int:
    return sum(1 for element in root.iter() if element.tag in tags)


def _strip_namespaces(tree) -> None:
    """Vendor files sometimes declare a default xmlns; plain tag lookup
    would then silently find nothing and yield an empty device."""
    for element in tree.iter():
        if isinstance(element.tag, str) and "}" in element.tag:
            element.tag = element.tag.rsplit("}", 1)[1]


def parse_file(path: str) -> SvdDevice:
    import os
    try:
        size = os.path.getsize(path)
    except OSError as error:
        raise ValueError(f"Cannot read file: {error}") from error
    if size == 0:
        raise ValueError("File is empty")
    if size > MAX_FILE_BYTES:
        raise ValueError(
            f"File is {size / 1024 / 1024:.1f} MB, over the "
            f"{MAX_FILE_BYTES / 1024 / 1024:.0f} MB safety limit; "
            "split it or use the CLI to inspect it in parts")
    parser = etree.XMLParser(huge_tree=True, no_network=True, resolve_entities=False,
                             remove_comments=True)
    try:
        tree = etree.parse(path, parser)
    except etree.XMLSyntaxError as error:
        raise ValueError(f"XML is not well-formed: {error}") from error
    except (OSError, ValueError) as error:
        raise ValueError(f"Cannot read file: {error}") from error
    _strip_namespaces(tree)
    root = tree.getroot()
    if root.tag != "device":
        raise ValueError(f"Root element is <{root.tag}>, expected <device>; not an SVD file")
    registers = sum(1 for _ in root.iter("register"))
    if registers > MAX_REGISTERS:
        raise ValueError(f"File declares {registers} registers, over the {MAX_REGISTERS} "
                         "safety limit; use the CLI to inspect it in parts")
    fields = sum(1 for _ in root.iter("field"))
    if fields > MAX_FIELDS:
        raise ValueError(f"File declares {fields} fields, over the {MAX_FIELDS} "
                         "safety limit; use the CLI to inspect it in parts")
    dev = SvdDevice(name=_t(root, "name"), version=_t(root, "version"),
                    description=_t(root, "description"), vendor=_t(root, "vendor"),
                    vendor_id=_t(root, "vendorID"), series=_t(root, "series"))
    dev.address_unit_bits = _i(root, "addressUnitBits", 8)
    dev.width = _i(root, "width", 32); dev.size = _i(root, "size", 32)
    dev.access = _t(root, "access"); dev.reset_value = _i(root, "resetValue", 0)
    cpu_el = root.find("cpu")
    if cpu_el is not None:
        dev.cpu = CpuInfo(name=_t(cpu_el, "name"), revision=_t(cpu_el, "revision"), endian=_t(cpu_el, "endian"),
                          mpu_present=_t(cpu_el, "mpuPresent") == "true", fpu_present=_t(cpu_el, "fpuPresent") == "true",
                          nvic_prio_bits=_i(cpu_el, "nvicPrioBits"),
                          vendor_systick_config=_t(cpu_el, "vendorSystickConfig") == "true")
        _mark_line(cpu_el, dev.cpu)
        _mark(cpu_el, dev.cpu, "name", "revision", "endian", "mpuPresent",
              "fpuPresent", "nvicPrioBits", "vendorSystickConfig")
    _mark(root, dev, "vendor", "vendorID", "name", "series", "version", "description",
          "licenseText", "addressUnitBits", "width", "size", "access", "protection",
          "resetValue", "resetMask", "cpu")
    for pn in root.findall("peripherals/peripheral"):
        dev.peripherals.append(_parse_peripheral(pn))
    dev.meta.source_file = path
    _mark_line(root, dev)
    return dev
