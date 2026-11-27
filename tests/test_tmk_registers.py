from zipfile import ZipFile

import pytest
from lxml import etree

from svdstudio.infrastructure.tmk_registers import (
    load_tmk_register_profile,
    load_tmk_register_profiles_from_jar,
    save_tmk_register_profile,
)

CPU_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<cpu id="TEST_CPU" description="Synthetic CPU &amp; status metadata">
  <register id="REG0" width="24" description="24-bit program state">
    <bitfield id="MODE" begin="23" end="21" description="Mode flags" access="RW"/>
    <bitfield id="RESERVED" begin="1" end="1" access="N"/>
    <bitfield id="READY" begin="0" end="0" access="R"/>
  </register>
  <register id="REG1" width="16"/>
</cpu>
"""
FPU_XML = b"""<cpu id="TEST_FPU">
  <register id="REG0" width="64"/>
  <register id="REG2" width="32"/>
</cpu>"""


@pytest.fixture
def profile_path(tmp_path):
    path = tmp_path / "test-cpu.xml"
    path.write_bytes(CPU_XML)
    return path


def test_standalone_profile_roundtrip(profile_path, tmp_path):
    group = load_tmk_register_profile(profile_path)
    mode, reserved, ready = group.registers[0].fields
    assert group.name == "TEST_CPU"
    assert group.description == "Synthetic CPU & status metadata"
    assert [register.size for register in group.registers] == [24, 16]
    assert (mode.bit_offset, mode.bit_width, mode.msb, mode.access) == (21, 3, 23, "RW")
    assert (reserved.lsb, reserved.msb, reserved.access) == (1, 1, "N")
    assert (ready.lsb, ready.msb, ready.access) == (0, 0, "R")

    out = tmp_path / "export.xml"
    save_tmk_register_profile(group, out)
    assert load_tmk_register_profile(out) == group
    expected = etree.parse(profile_path, etree.XMLParser(remove_blank_text=True))
    actual = etree.parse(out, etree.XMLParser(remove_blank_text=True))
    assert etree.tostring(expected, method="c14n") == etree.tostring(actual, method="c14n")


def test_import_both_plugin_profiles(tmp_path):
    path = tmp_path / "debug-core.jar"
    with ZipFile(path, "w") as archive:
        archive.writestr("cn/com/tmkstudio/debug/registers/c28xx.xml", CPU_XML)
        archive.writestr("cn/com/tmkstudio/debug/registers/c28xx-fpu.xml", FPU_XML)
        archive.writestr("unrelated.xml", b"invalid")

    core, fpu = load_tmk_register_profiles_from_jar(path)
    assert (core.name, fpu.name) == ("TEST_CPU", "TEST_FPU")
    assert core.registers[0].name == fpu.registers[0].name == "REG0"
    assert fpu.registers[0].size == 64


def test_missing_profile_in_plugin(tmp_path):
    path = tmp_path / "wrong-plugin.jar"
    with ZipFile(path, "w") as archive:
        archive.writestr("cn/com/tmkstudio/debug/registers/c28xx.xml", CPU_XML)
    with pytest.raises(ValueError, match="c28xx-fpu.xml"):
        load_tmk_register_profiles_from_jar(path)


@pytest.mark.parametrize(
    ("xml", "message"),
    [
        (b"<device/>", "Expected <cpu>"),
        (b'<!DOCTYPE cpu><cpu id="TEST"/>', "DOCTYPE"),
        (b'<cpu id="TEST" address="0"/>', "Unsupported attributes"),
        (CPU_XML.replace(b'begin="23"', b'begin="24"'), "bit range"),
        (CPU_XML.replace(b'id="REG1"', b'id="reg0"'), "Duplicate identifier"),
    ],
)
def test_rejects_unsupported_or_invalid_profile(xml, message, tmp_path):
    path = tmp_path / "invalid.xml"
    path.write_bytes(xml)
    with pytest.raises(ValueError, match=message):
        load_tmk_register_profile(path)


def test_export_validates_before_overwriting(profile_path, tmp_path):
    group = load_tmk_register_profile(profile_path)
    group.registers[0].reset_value = 0
    out = tmp_path / "protected.xml"
    out.write_bytes(CPU_XML)
    with pytest.raises(ValueError, match="cannot represent register access or reset metadata"):
        save_tmk_register_profile(group, out)
    assert out.read_bytes() == CPU_XML


def test_export_maps_supported_cmsis_access(profile_path, tmp_path):
    group = load_tmk_register_profile(profile_path)
    group.registers[0].fields[0].access = "write-only"
    out = tmp_path / "export.xml"
    save_tmk_register_profile(group, out)
    assert load_tmk_register_profile(out).registers[0].fields[0].access == "W"
