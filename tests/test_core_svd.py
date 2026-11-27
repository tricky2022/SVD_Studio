from pathlib import Path

import pytest
from lxml import etree

from svdstudio.domain.model import (
    CoreRegister,
    CoreRegisterGroup,
    EnumeratedValues,
    EnumValue,
    SvdField,
)
from svdstudio.infrastructure.svd_parser import CORE_REGISTERS_NS, parse_file
from svdstudio.serializers import svd_writer

FIXTURE = Path(__file__).parent / "fixtures" / "simple.svd"
NS = {"core": CORE_REGISTERS_NS}
SCHEMA_ATTR = "{http://www.w3.org/2001/XMLSchema-instance}noNamespaceSchemaLocation"


def test_core_groups_are_round_tripped_separately_from_mmio(tmp_path):
    device = parse_file(str(FIXTURE))
    field = SvdField(name="MODE", bit_offset=61, bit_width=3, access="R",
                     enumerated_values=[EnumeratedValues(values=[EnumValue("READY", value=1)])])
    device.core_register_groups = [
        CoreRegisterGroup("TMS320C28XX", "CPU", [CoreRegister("ACC", 64, fields=[field])]),
        CoreRegisterGroup("TMK_SIMULATOR_FPU", registers=[CoreRegister("ACC", 32, reset_value=0)]),
    ]
    out = tmp_path / "core.svd"
    svd_writer.write_file(device, str(out))

    root = etree.parse(out)
    assert root.find("cpu") is None
    assert [item.findtext("name") for item in root.findall("peripherals/peripheral")] == [
        "GPIOA", "GPIOB",
    ]
    groups = root.findall("vendorExtensions/core:coreRegisters/core:group", NS)
    assert [group.get("name") for group in groups] == ["TMS320C28XX", "TMK_SIMULATOR_FPU"]
    assert all(group.find("core:register", NS).get("name") == "ACC" for group in groups)
    assert root.find(".//core:addressOffset", NS) is None

    restored = parse_file(str(out))
    cpu, fpu = restored.core_register_groups
    assert cpu.description == "CPU"
    register = cpu.registers[0]
    assert register.size == 64
    assert register.reset_value is None
    assert register.reset_mask is None
    assert register.reset_mask_value == 0xFFFFFFFFFFFFFFFF
    restored_field = register.fields[0]
    assert (restored_field.lsb, restored_field.msb, restored_field.access) == (61, 63, "R")
    assert restored_field.enumerated_values[0].values[0].value == 1
    assert fpu.registers[0].reset_value == 0


def test_namespaced_input_keeps_foreign_vendor_element_names(tmp_path):
    source = tmp_path / "namespaced.svd"
    source.write_text(
        '<device xmlns="urn:input"><name>TEST</name><cpu><name>CM33</name>'
        '<sauRegionsConfig><region/></sauRegionsConfig></cpu>'
        '<vendorExtensions><data/><empty xmlns=""/></vendorExtensions></device>',
        encoding="utf-8",
    )
    root = etree.fromstring(svd_writer.serialize_device(parse_file(str(source))))
    assert root.findtext("name") == "TEST"
    assert root.find("cpu/sauRegionsConfig/region") is not None
    assert root.find("vendorExtensions/{urn:input}data") is not None
    assert root.find("vendorExtensions/empty") is not None


@pytest.mark.parametrize(("content", "error"), [
    ('<core:group name="CPU" unknown="data"/>', "Unsupported core group attributes unknown"),
    ('<core:group name="CPU"><core:unknown/></core:group>', "Unsupported element.*in core group"),
    ('<core:group name="CPU"><register name="PC" size="32"/></core:group>',
     "Unsupported element register in core group"),
    ((
        '<core:group name="CPU"><core:register name="PC" size="32"><core:fields>'
        '<core:field><core:name>FLAG</core:name><core:unknown/></core:field></core:fields>'
        '</core:register></core:group>'
    ), "Unsupported element.*in core field"),
])
def test_core_extension_rejects_unrepresentable_xml(tmp_path, content, error):
    source = tmp_path / "unexpected.svd"
    source.write_text(
        f'<device xmlns:core="{CORE_REGISTERS_NS}"><vendorExtensions>'
        f'<core:coreRegisters>{content}</core:coreRegisters></vendorExtensions></device>',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=error):
        parse_file(str(source))


def test_standard_cpu_and_unrelated_vendor_xml_survive_edit(tmp_path):
    source = tmp_path / "input.svd"
    source.write_text(FIXTURE.read_text(encoding="utf-8").replace(
        '<device schemaVersion="1.3">',
        '<device xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" schemaVersion="1.3"'
        ' xsi:noNamespaceSchemaLocation="CMSIS-SVD.xsd">',
    ).replace(
        "  <addressUnitBits>",
        """  <licenseText>License information</licenseText>
  <cpu>
    <name>CM33</name><revision>r0p0</revision><endian>little</endian>
    <mpuPresent>1</mpuPresent><fpuPresent>0</fpuPresent><dspPresent>false</dspPresent>
    <nvicPrioBits>3</nvicPrioBits><vendorSystickConfig>false</vendorSystickConfig>
    <deviceNumInterrupts>0</deviceNumInterrupts><sauNumRegions>2</sauNumRegions>
    <sauRegionsConfig enabled="false" protectionWhenDisabled="n">
      <region name="region1"><base>0x4000</base><limit>0x5000</limit><access>n</access></region>
    </sauRegionsConfig>
  </cpu>
  <headerSystemFilename>system_test</headerSystemFilename>
  <headerDefinitionsPrefix>Test</headerDefinitionsPrefix>
  <addressUnitBits>""",
    ).replace(
        "  <peripherals>", "  <protection>p</protection><resetMask>0xFFFF</resetMask>\n  <peripherals>",
    ).replace(
        "</device>",
        """  <vendorExtensions xmlns:vendor="urn:vendor-integration">
    <!-- retained note -->
    <vendor:setting vendor:revision="4"><vendor:value>enabled</vendor:value></vendor:setting>
  </vendorExtensions>
</device>""",
    ), encoding="utf-8")

    device = parse_file(str(source))
    assert device.cpu.mpu_present is True and device.cpu.fpu_present is False
    assert device.cpu.dsp_present is False and device.cpu.fpu_dp is None
    assert device.cpu.device_num_interrupts == 0
    device.cpu.vtor_present = False
    device.core_register_groups.append(CoreRegisterGroup("CPU"))
    out = tmp_path / "combined.svd"
    svd_writer.write_file(device, str(out))
    root = etree.parse(out)
    assert root.getroot().get(SCHEMA_ATTR) == "CMSIS-SVD.xsd"
    assert root.findtext("licenseText") == "License information"
    assert root.findtext("headerSystemFilename") == "system_test"
    assert root.findtext("headerDefinitionsPrefix") == "Test"
    assert root.findtext("resetMask") == "0xffff"
    assert root.findtext("protection") == "p"
    assert root.findtext("cpu/fpuPresent") == "false"
    assert root.find("cpu/fpuDP") is None
    assert root.findtext("cpu/vtorPresent") == "false"
    assert root.findtext("cpu/deviceNumInterrupts") == "0"
    assert root.findtext("cpu/sauRegionsConfig/region/base") == "0x4000"
    vendor = root.find("vendorExtensions")
    assert vendor.find("{urn:vendor-integration}setting").get("{urn:vendor-integration}revision") == "4"
    assert vendor.findtext("{urn:vendor-integration}setting/{urn:vendor-integration}value") == "enabled"
    assert vendor.xpath("comment()")[0].text == " retained note "

    restored = parse_file(str(out))
    restored.core_register_groups.clear()
    saved_again = etree.fromstring(svd_writer.serialize_device(restored))
    assert saved_again.find("vendorExtensions/{urn:vendor-integration}setting") is not None
    assert saved_again.find("vendorExtensions/core:coreRegisters", NS) is None


def test_save_keeps_existing_bytes_and_cleans_temporary_file_when_replacement_fails(tmp_path, monkeypatch):
    output = tmp_path / "device.svd"
    output.write_bytes(b"previous version")

    def fail_replace(_source, _target):
        raise PermissionError("destination is locked")

    monkeypatch.setattr(svd_writer.os, "replace", fail_replace)
    with pytest.raises(PermissionError, match="destination is locked"):
        svd_writer.write_file(parse_file(str(FIXTURE)), str(output))
    assert output.read_bytes() == b"previous version"
    assert list(tmp_path.iterdir()) == [output]
