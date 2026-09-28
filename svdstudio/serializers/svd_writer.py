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
    SvdInterrupt,
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
    if enum_values.header_enum_name:
        _sub(element, "headerEnumName", enum_values.header_enum_name)
    if enum_values.usage:
        _sub(element, "usage", enum_values.usage)
    for value in enum_values.values:
        value_element = _sub(element, "enumeratedValue")
        _sub(value_element, "name", value.name)
        if value.description:
            _sub(value_element, "description", value.description)
        _sub(value_element, "value", _hex(value.value))
        if value.is_default:
            _sub(value_element, "isDefault", "true")


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
    _sub(element, "name", field.name)
    if field.description:
        _sub(element, "description", field.description)
    _write_dim(element, field.dim)
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
    if field.read_action:
        _sub(element, "readAction", field.read_action)
    if field.modified_write_values:
        _sub(element, "modifiedWriteValues", field.modified_write_values)
    if field.write_constraint or field.write_constraint_min is not None \
            or field.write_constraint_max is not None:
        _emit_write_constraint(element, "writeConstraint", field.write_constraint,
                               field.write_constraint_min, field.write_constraint_max)
    for enum_values in field.enumerated_values:
        _write_enum(element, enum_values)


def _write_register(parent, register: SvdRegister) -> None:
    present = register.meta.present if register.meta is not None else set()
    attrs = {"derivedFrom": register.derived_from} if register.derived_from else {}
    element = etree.SubElement(parent, "register", **attrs)
    if register.name:
        _sub(element, "name", register.name)
    if register.display_name:
        _sub(element, "displayName", register.display_name)
    if register.description:
        _sub(element, "description", register.description)
    if "dim" in present:
        _write_dim(element, register.dim)
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
    if ("readAction" in present or register.read_action):
        _sub(element, "readAction", register.read_action)
    if ("modifiedWriteValues" in present or register.modified_write_values):
        _sub(element, "modifiedWriteValues", register.modified_write_values)
    if ("writeConstraint" in present or register.write_constraint
            or register.write_constraint_min is not None
            or register.write_constraint_max is not None):
        _emit_write_constraint(element, "writeConstraint", register.write_constraint,
                              register.write_constraint_min, register.write_constraint_max)
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


def _cpu_has_content(cpu: CpuInfo) -> bool:
    return any((cpu.name, cpu.revision, cpu.endian, cpu.mpu_present, cpu.fpu_present,
                cpu.nvic_prio_bits, cpu.vendor_systick_config))


def _write_cpu(parent, cpu: CpuInfo) -> None:
    element = _sub(parent, "cpu")
    present = cpu.meta.present if cpu.meta is not None else set()

    for tag, value in (("name", cpu.name), ("revision", cpu.revision), ("endian", cpu.endian)):
        if value and (tag in present or value):
            _sub(element, tag, value)
    if (cpu.mpu_present or "mpuPresent" in present):
        _sub(element, "mpuPresent", str(cpu.mpu_present).lower())
    if (cpu.fpu_present or "fpuPresent" in present):
        _sub(element, "fpuPresent", str(cpu.fpu_present).lower())
    if (cpu.nvic_prio_bits or "nvicPrioBits" in present):
        _sub(element, "nvicPrioBits", cpu.nvic_prio_bits)
    if (cpu.vendor_systick_config or "vendorSystickConfig" in present):
        _sub(element, "vendorSystickConfig", str(cpu.vendor_systick_config).lower())


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
        if value and tag in present:
            _sub(root, tag, value)
    if "cpu" in present or _cpu_has_content(device.cpu):
        _write_cpu(root, device.cpu)
    if "addressUnitBits" in present:
        _sub(root, "addressUnitBits", device.address_unit_bits)
    if "width" in present:
        _sub(root, "width", device.width)
    if "size" in present and device.size:
        _sub(root, "size", device.size)
    if "access" in present and device.access:
        _sub(root, "access", device.access)
    if "protection" in present and device.protection:
        _sub(root, "protection", device.protection)
    if "resetValue" in present:
        _sub(root, "resetValue", _hex(device.reset_value))
    if "resetMask" in present:
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
        if peripheral.disable_condition:
            _sub(element, "disableCondition", peripheral.disable_condition)
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
    return etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="utf-8")


def write_file(device: SvdDevice, path: str) -> None:
    with open(path, "wb") as handle:
        handle.write(serialize_device(device))
