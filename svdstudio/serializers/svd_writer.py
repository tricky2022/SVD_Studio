"""Domain -> CMSIS-SVD XML serializer."""
from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

from lxml import etree

from svdstudio.domain.model import (
    CPU_PROPERTIES,
    AddressBlock,
    CpuInfo,
    EnumeratedValues,
    SvdCluster,
    SvdDevice,
    SvdField,
    SvdInterrupt,
    SvdRegister,
)
from svdstudio.infrastructure.svd_parser import CORE_REGISTERS_NS


def _sub(parent, tag: str, value=None):
    element = etree.SubElement(parent, tag)
    if value is not None:
        element.text = str(value)
    return element


def _hex(value: int) -> str:
    return hex(value)


def _write_dim(parent, dim) -> None:
    if not dim.dim:
        return
    _sub(parent, "dim", dim.dim)
    _sub(parent, "dimIncrement", _hex(dim.dim_increment))
    if dim.dim_index:
        _sub(parent, "dimIndex", ",".join(dim.dim_index))


def _write_enum(parent, enum_values: EnumeratedValues) -> None:
    attrs = {"derivedFrom": enum_values.derived_from} if enum_values.derived_from else {}
    element = etree.SubElement(parent, "enumeratedValues", **attrs)
    if enum_values.name:
        _sub(element, "name", enum_values.name)
    if enum_values.header_enum_name:
        _sub(element, "headerEnumName", enum_values.header_enum_name)
    if enum_values.usage:
        _sub(element, "usage", enum_values.usage)
    for value in enum_values.values:
        value_element = _sub(element, "enumeratedValue")
        _sub(value_element, "name", value.name)
        if value.description:
            _sub(value_element, "description", value.description)
        if value.is_default:
            _sub(value_element, "isDefault", "true")
        else:
            _sub(value_element, "value", _hex(value.value))


def _emit_write_constraint(parent, tag, constr: str, minimum, maximum) -> None:
    """Emit writeConstraint using the schema's child-element structure.

    CMSIS-SVD models writeConstraint as a choice of child elements; unknown
    (vendor) values are preserved as plain text so nothing is dropped.
    """
    if not constr:
        return
    element = etree.SubElement(parent, tag)
    if constr == "range":
        if minimum is None and maximum is None:
            element.text = "range"
            return
        rg = _sub(element, "range")
        if minimum is not None:
            _sub(rg, "minimum", minimum)
        if maximum is not None:
            _sub(rg, "maximum", maximum)
    elif constr == "writeAsRead":
        _sub(element, "writeAsRead", "true")
    elif constr == "useEnumeratedValues":
        _sub(element, "useEnumeratedValues", "true")
    else:
        # legacy / unknown value: preserve verbatim as element text
        element.text = constr


def _write_field(parent, field: SvdField) -> None:
    attrs = {"derivedFrom": field.derived_from} if field.derived_from else {}
    element = etree.SubElement(parent, "field", **attrs)
    _write_dim(element, field.dim)
    _sub(element, "name", field.name)
    if field.description:
        _sub(element, "description", field.description)
    # preserve the authorial bit-range form rather than normalizing to
    # bitOffset/bitWidth (a present single-bit msb=0 or a bitRange survives)
    if field.source_range_form == "bitRange":
        _sub(element, "bitRange", f"[{field.msb}:{field.lsb}]")
    elif field.source_range_form == "lsb_msb":
        _sub(element, "lsb", field.lsb)
        _sub(element, "msb", field.msb)
    else:
        _sub(element, "bitOffset", field.bit_offset)
        _sub(element, "bitWidth", field.bit_width)
    if field.access:
        _sub(element, "access", field.access)
    if field.reset_value is not None:
        _sub(element, "resetValue", _hex(field.reset_value))
    if field.modified_write_values:
        _sub(element, "modifiedWriteValues", field.modified_write_values)
    if field.write_constraint or field.write_constraint_min is not None \
            or field.write_constraint_max is not None:
        _emit_write_constraint(element, "writeConstraint", field.write_constraint,
                               field.write_constraint_min, field.write_constraint_max)
    if field.read_action:
        _sub(element, "readAction", field.read_action)
    for enum_values in field.enumerated_values:
        _write_enum(element, enum_values)


def _write_register(parent, register: SvdRegister) -> None:
    present = register.meta.present if register.meta is not None else set()
    attrs = {"derivedFrom": register.derived_from} if register.derived_from else {}
    element = etree.SubElement(parent, "register", **attrs)
    _write_dim(element, register.dim)
    if register.name:
        _sub(element, "name", register.name)
    if register.display_name:
        _sub(element, "displayName", register.display_name)
    if register.description:
        _sub(element, "description", register.description)
    if register.alternate_register:
        _sub(element, "alternateRegister", register.alternate_register)
    _sub(element, "addressOffset", _hex(register.address_offset))
    if register.size is not None:
        _sub(element, "size", register.size)
    if ("access" in present or register.access):
        _sub(element, "access", register.access)
    if ("protection" in present or register.protection):
        _sub(element, "protection", register.protection)
    if register.reset_value is not None:
        _sub(element, "resetValue", _hex(register.reset_value))
    if register.reset_mask is not None:
        _sub(element, "resetMask", _hex(register.reset_mask))
    if ("modifiedWriteValues" in present or register.modified_write_values):
        _sub(element, "modifiedWriteValues", register.modified_write_values)
    if ("writeConstraint" in present or register.write_constraint
            or register.write_constraint_min is not None
            or register.write_constraint_max is not None):
        _emit_write_constraint(element, "writeConstraint", register.write_constraint,
                              register.write_constraint_min, register.write_constraint_max)
    if ("readAction" in present or register.read_action):
        _sub(element, "readAction", register.read_action)
    for enum_values in register.enumerated_values:
        _write_enum(element, enum_values)
    if register.fields:
        fields_element = _sub(element, "fields")
        for field in register.fields:
            _write_field(fields_element, field)


def _write_cluster(parent, cluster: SvdCluster) -> None:
    attrs = {"derivedFrom": cluster.derived_from} if cluster.derived_from else {}
    element = etree.SubElement(parent, "cluster", **attrs)
    _write_dim(element, cluster.dim)
    _sub(element, "name", cluster.name)
    if cluster.description:
        _sub(element, "description", cluster.description)
    if cluster.alternate_cluster:
        _sub(element, "alternateCluster", cluster.alternate_cluster)
    _sub(element, "addressOffset", _hex(cluster.address_offset))
    if cluster.registers or cluster.clusters:
        for register in cluster.registers:
            _write_register(element, register)
        for nested in cluster.clusters:
            _write_cluster(element, nested)


def _parse_fragment(xml: bytes):
    parser = etree.XMLParser(huge_tree=True, no_network=True, resolve_entities=False)
    return etree.fromstring(xml, parser)


def _write_cpu(parent, cpu: CpuInfo, present: bool) -> None:
    defaults = CpuInfo()
    values = []
    for tag, attr, kind in CPU_PROPERTIES:
        value = getattr(cpu, attr)
        if value is not None and (tag in cpu.meta.present or value != getattr(defaults, attr)):
            values.append((tag, str(value).lower() if kind is bool else value))
    if present or values or cpu.sau_regions_config_xml:
        element = _sub(parent, "cpu")
        for tag, value in values:
            _sub(element, tag, value)
        if cpu.sau_regions_config_xml:
            element.append(_parse_fragment(cpu.sau_regions_config_xml))


def _write_vendor_extensions(root, device: SvdDevice) -> None:
    if not device.vendor_extensions_xml and not device.core_register_groups:
        return
    if device.vendor_extensions_xml:
        opaque = _parse_fragment(device.vendor_extensions_xml)
        namespaces = {prefix: uri for prefix, uri in opaque.nsmap.items() if prefix is not None}
        vendor = etree.SubElement(root, "vendorExtensions", attrib=opaque.attrib, nsmap=namespaces)
        vendor.text = opaque.text
        vendor.extend(opaque)
    else:
        vendor = _sub(root, "vendorExtensions")
    if not device.core_register_groups:
        return
    core = etree.SubElement(vendor, f"{{{CORE_REGISTERS_NS}}}coreRegisters",
                            nsmap={"svdstudio": CORE_REGISTERS_NS})
    for group in device.core_register_groups:
        group_xml = etree.SubElement(core, "group", name=group.name)
        if group.description:
            group_xml.set("description", group.description)
        for register in group.registers:
            register_xml = etree.SubElement(group_xml, "register", name=register.name,
                                            size=str(register.size))
            if register.description:
                register_xml.set("description", register.description)
            if register.access:
                register_xml.set("access", register.access)
            if register.reset_value is not None:
                register_xml.set("resetValue", _hex(register.reset_value))
            if register.reset_mask is not None:
                register_xml.set("resetMask", _hex(register.reset_mask))
            if register.fields:
                fields = _sub(register_xml, "fields")
                for field in register.fields:
                    _write_field(fields, field)
    for child in core.iterdescendants():
        child.tag = f"{{{CORE_REGISTERS_NS}}}{child.tag}"


def _write_address_block(parent, block: AddressBlock) -> None:
    element = _sub(parent, "addressBlock")
    _sub(element, "offset", _hex(block.offset))
    _sub(element, "size", _hex(block.size))
    _sub(element, "usage", block.usage)


def _write_interrupt(parent, interrupt: SvdInterrupt) -> None:
    present = interrupt.meta.present if interrupt.meta is not None else set()
    element = _sub(parent, "interrupt")
    if interrupt.name or "name" in present:
        _sub(element, "name", interrupt.name)
    if interrupt.description or "description" in present:
        _sub(element, "description", interrupt.description)
    if "value" in present or interrupt.value:
        _sub(element, "value", _hex(interrupt.value))


def serialize_device(device: SvdDevice) -> bytes:
    present = device.meta.present if device.meta is not None else set()
    root = etree.Element("device", attrib={**device.xml_attributes,
                                           "schemaVersion": device.schema_version},
                         nsmap=device.xml_namespaces)
    for tag, value in (
        ("vendor", device.vendor),
        ("vendorID", device.vendor_id),
        ("name", device.name),
        ("series", device.series),
        ("version", device.version),
        ("description", device.description),
        ("licenseText", device.license_text),
    ):
        if value:
            _sub(root, tag, value)
    _write_cpu(root, device.cpu, "cpu" in present)
    for tag, value in (("headerSystemFilename", device.header_system_filename),
                       ("headerDefinitionsPrefix", device.header_definitions_prefix)):
        if value:
            _sub(root, tag, value)
    _sub(root, "addressUnitBits", device.address_unit_bits)
    _sub(root, "width", device.width)
    if "size" in present or device.size != 32:
        _sub(root, "size", device.size)
    if device.access:
        _sub(root, "access", device.access)
    if device.protection:
        _sub(root, "protection", device.protection)
    if "resetValue" in present or device.reset_value != 0:
        _sub(root, "resetValue", _hex(device.reset_value))
    if "resetMask" in present or device.reset_mask != 0xFFFFFFFF:
        _sub(root, "resetMask", _hex(device.reset_mask))

    peripherals = _sub(root, "peripherals")
    for peripheral in device.peripherals:
        attrs = {"derivedFrom": peripheral.derived_from} if peripheral.derived_from else {}
        element = etree.SubElement(peripherals, "peripheral", **attrs)
        _write_dim(element, peripheral.dim)
        _sub(element, "name", peripheral.name)
        if peripheral.display_name:
            _sub(element, "displayName", peripheral.display_name)
        if peripheral.description:
            _sub(element, "description", peripheral.description)
        if peripheral.group_name:
            _sub(element, "groupName", peripheral.group_name)
        for tag, value in (("prependToName", peripheral.prepend_to_name),
                           ("appendToName", peripheral.append_to_name),
                           ("headerStructName", peripheral.header_struct_name)):
            if value:
                _sub(element, tag, value)
        if peripheral.disable_condition:
            _sub(element, "disableCondition", peripheral.disable_condition)
        _sub(element, "baseAddress", _hex(peripheral.base_address))
        for block in peripheral.address_blocks:
            _write_address_block(element, block)
        for interrupt in peripheral.interrupts:
            _write_interrupt(element, interrupt)
        if peripheral.registers or peripheral.clusters:
            registers = _sub(element, "registers")
            for register in peripheral.registers:
                _write_register(registers, register)
            for cluster in peripheral.clusters:
                _write_cluster(registers, cluster)
    _write_vendor_extensions(root, device)
    return etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="utf-8")


def write_file(device: SvdDevice, path: str) -> None:
    data = serialize_device(device)
    target = Path(path).resolve()
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=f".{target.name}.",
                                         suffix=".tmp", delete=False) as handle:
            temp_path = Path(handle.name)
            handle.write(data)
        if os.name != "nt" and target.exists():
            os.chmod(temp_path, stat.S_IMODE(target.stat().st_mode))
        os.replace(temp_path, target)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
