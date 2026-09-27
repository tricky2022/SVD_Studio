"""Domain -> CMSIS-SVD XML serializer."""
from __future__ import annotations

from lxml import etree

from svdstudio.domain.model import (
    AddressBlock,
    CpuInfo,
    EnumeratedValues,
    SvdCluster,
    SvdDevice,
    SvdField,
    SvdRegister,
)


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
    if enum_values.usage:
        _sub(element, "usage", enum_values.usage)
    for value in enum_values.values:
        value_element = _sub(element, "enumeratedValue")
        _sub(value_element, "name", value.name)
        if value.description:
            _sub(value_element, "description", value.description)
        _sub(value_element, "value", _hex(value.value))


def _write_field(parent, field: SvdField) -> None:
    attrs = {"derivedFrom": field.derived_from} if field.derived_from else {}
    element = etree.SubElement(parent, "field", **attrs)
    _sub(element, "name", field.name)
    if field.description:
        _sub(element, "description", field.description)
    _write_dim(element, field.dim)
    _sub(element, "bitOffset", field.bit_offset)
    _sub(element, "bitWidth", field.bit_width)
    if field.access:
        _sub(element, "access", field.access)
    if field.reset_value is not None:
        _sub(element, "resetValue", _hex(field.reset_value))
    if field.read_action:
        _sub(element, "readAction", field.read_action)
    if field.modified_write_values:
        _sub(element, "modifiedWriteValues", field.modified_write_values)
    if field.write_constraint:
        _sub(element, "writeConstraint", field.write_constraint)
    for enum_values in field.enumerated_values:
        _write_enum(element, enum_values)


def _write_register(parent, register: SvdRegister) -> None:
    attrs = {"derivedFrom": register.derived_from} if register.derived_from else {}
    element = etree.SubElement(parent, "register", **attrs)
    _sub(element, "name", register.name)
    if register.display_name:
        _sub(element, "displayName", register.display_name)
    if register.description:
        _sub(element, "description", register.description)
    _write_dim(element, register.dim)
    _sub(element, "addressOffset", _hex(register.address_offset))
    _sub(element, "size", register.size)
    if register.access:
        _sub(element, "access", register.access)
    if register.protection:
        _sub(element, "protection", register.protection)
    _sub(element, "resetValue", _hex(register.reset_value))
    _sub(element, "resetMask", _hex(register.reset_mask))
    if register.read_action:
        _sub(element, "readAction", register.read_action)
    if register.modified_write_values:
        _sub(element, "modifiedWriteValues", register.modified_write_values)
    if register.write_constraint:
        _sub(element, "writeConstraint", register.write_constraint)
    if register.alternate_register:
        _sub(element, "alternateRegister", register.alternate_register)
    for enum_values in register.enumerated_values:
        _write_enum(element, enum_values)
    if register.fields:
        fields_element = _sub(element, "fields")
        for field in register.fields:
            _write_field(fields_element, field)


def _write_cluster(parent, cluster: SvdCluster) -> None:
    attrs = {"derivedFrom": cluster.derived_from} if cluster.derived_from else {}
    element = etree.SubElement(parent, "cluster", **attrs)
    _sub(element, "name", cluster.name)
    if cluster.description:
        _sub(element, "description", cluster.description)
    _write_dim(element, cluster.dim)
    _sub(element, "addressOffset", _hex(cluster.address_offset))
    if cluster.alternate_cluster:
        _sub(element, "alternateCluster", cluster.alternate_cluster)
    if cluster.registers or cluster.clusters:
        for register in cluster.registers:
            _write_register(element, register)
        for nested in cluster.clusters:
            _write_cluster(element, nested)


def _write_cpu(parent, cpu: CpuInfo) -> None:
    element = _sub(parent, "cpu")
    for tag, value in (("name", cpu.name), ("revision", cpu.revision), ("endian", cpu.endian)):
        if value:
            _sub(element, tag, value)
    _sub(element, "mpuPresent", str(cpu.mpu_present).lower())
    _sub(element, "fpuPresent", str(cpu.fpu_present).lower())
    _sub(element, "nvicPrioBits", cpu.nvic_prio_bits)
    _sub(element, "vendorSystickConfig", str(cpu.vendor_systick_config).lower())


def _write_address_block(parent, block: AddressBlock) -> None:
    element = _sub(parent, "addressBlock")
    _sub(element, "offset", _hex(block.offset))
    _sub(element, "size", _hex(block.size))
    _sub(element, "usage", block.usage)


def serialize_device(device: SvdDevice) -> bytes:
    root = etree.Element("device", attrib={"schemaVersion": "1.3"})
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
    _write_cpu(root, device.cpu)
    _sub(root, "addressUnitBits", device.address_unit_bits)
    _sub(root, "width", device.width)
    if device.size:
        _sub(root, "size", device.size)
    if device.access:
        _sub(root, "access", device.access)
    if device.protection:
        _sub(root, "protection", device.protection)
    _sub(root, "resetValue", _hex(device.reset_value))
    _sub(root, "resetMask", _hex(device.reset_mask))

    peripherals = _sub(root, "peripherals")
    for peripheral in device.peripherals:
        attrs = {"derivedFrom": peripheral.derived_from} if peripheral.derived_from else {}
        element = etree.SubElement(peripherals, "peripheral", **attrs)
        _sub(element, "name", peripheral.name)
        if peripheral.display_name:
            _sub(element, "displayName", peripheral.display_name)
        if peripheral.description:
            _sub(element, "description", peripheral.description)
        if peripheral.group_name:
            _sub(element, "groupName", peripheral.group_name)
        _write_dim(element, peripheral.dim)
        _sub(element, "baseAddress", _hex(peripheral.base_address))
        for tag, value in (("prependToName", peripheral.prepend_to_name),
                           ("appendToName", peripheral.append_to_name),
                           ("headerStructName", peripheral.header_struct_name)):
            if value:
                _sub(element, tag, value)
        for block in peripheral.address_blocks:
            _write_address_block(element, block)
        if peripheral.registers or peripheral.clusters:
            registers = _sub(element, "registers")
            for register in peripheral.registers:
                _write_register(registers, register)
            for cluster in peripheral.clusters:
                _write_cluster(registers, cluster)
    return etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="utf-8")


def write_file(device: SvdDevice, path: str) -> None:
    with open(path, "wb") as handle:
        handle.write(serialize_device(device))
