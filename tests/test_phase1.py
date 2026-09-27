import os

from svdstudio.application.commands import DeleteCommand, InsertCommand
from svdstudio.application.tabular_import import import_file
from svdstudio.domain.effective import resolve_derived_peripherals
from svdstudio.domain.model import AddressBlock, SvdRegister
from svdstudio.infrastructure import svd_parser
from svdstudio.serializers import svd_writer
from svdstudio.validators import validate as V

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "simple.svd")

def test_parse():
    d = svd_parser.parse_file(FIX)
    assert d.name == "TESTDEV" and len(d.peripherals) == 2
    assert d.peripherals[0].registers[0].fields[0].name == "MODE0"

def test_roundtrip(tmp_path):
    d = svd_parser.parse_file(FIX)
    out = str(tmp_path / "out.svd")
    svd_writer.write_file(d, out)
    d2 = svd_parser.parse_file(out)
    assert d2.peripherals[0].registers[0].fields[1].bit_width == 2

def test_semantic_overlap():
    d = svd_parser.parse_file(FIX)
    d.peripherals[0].registers[0].fields[1].bit_offset = 0
    iss = V.semantic_check(d)
    assert any(i.rule_id == "SVD-FIELD-002" for i in iss)

def test_derived_chain():
    d = svd_parser.parse_file(FIX)
    assert resolve_derived_peripherals(d)["GPIOB"] == ["GPIOB", "GPIOA"]

def test_domain_has_no_qt():
    import svdstudio.domain.model as m
    assert not any("PySide" in str(v) for v in vars(m).values())


def test_roundtrip_preserves_device_and_register_semantics(tmp_path):
    device = svd_parser.parse_file(FIX)
    device.cpu.name = "CM4"
    device.peripherals[0].address_blocks.append(
        AddressBlock(offset=0, size=0x400, usage="registers")
    )
    register = device.peripherals[0].registers[0]
    register.read_action = "clear"
    register.modified_write_values = "oneToClear"
    register.write_constraint = "nonzero"
    out = str(tmp_path / "semantic.svd")
    svd_writer.write_file(device, out)
    restored = svd_parser.parse_file(out)
    restored_register = restored.peripherals[0].registers[0]
    assert restored.cpu.name == "CM4"
    assert len(restored.peripherals[0].address_blocks) == 1
    assert restored_register.read_action == "clear"
    assert restored_register.modified_write_values == "oneToClear"
    assert restored_register.write_constraint == "nonzero"


def test_tabular_import_builds_domain(tmp_path):
    source = os.path.join(os.path.dirname(__file__), "fixtures", "registers.csv")
    result = import_file(source, "DSPDEV")
    assert result.valid
    assert result.peripherals_created == 1
    assert result.registers_created == 2
    assert result.fields_created == 3
    field = result.device.peripherals[0].registers[0].fields[0]
    assert field.name == "ENABLE"
    assert [item.name for item in field.enumerated_values[0].values] == ["DISABLED", "ENABLED"]


def test_tabular_import_reports_missing_required_columns(tmp_path):
    source = tmp_path / "invalid.csv"
    source.write_text("Peripheral\nDSP\n", encoding="utf-8")
    result = import_file(str(source), "DSPDEV")
    assert any(issue.severity == "error" for issue in result.issues)


def test_path_search_and_address_lookup():
    from svdstudio.domain import search_utils as SU
    device = svd_parser.parse_file(FIX)
    hits = SU.search(device, "GPIOA.MODER.MODE0")
    assert hits and hits[0].path == "GPIOA.MODER.MODE0"
    addr_hits = SU.address_lookup(device, 0x40010800)
    assert any(h.path == "GPIOA.MODER" for h in addr_hits)


def test_device_diff_detects_property_change():
    from svdstudio.domain import diff as DD
    old = svd_parser.parse_file(FIX)
    new = svd_parser.parse_file(FIX)
    new.peripherals[0].registers[0].reset_value = 0x40
    report = DD.diff_devices(old, new)
    assert any(e.path == "GPIOA.MODER.reset_value" and e.new == "64" for e in report.entries)


def test_overlay_applies_and_conflicts():
    from svdstudio.domain import overlay as OV
    device = svd_parser.parse_file(FIX)
    effective, result = OV.apply_overlay(device, {"GPIOA.MODER.access": "read-only",
                                                  "NOPE.X.access": "rw"})
    assert result.applied == ["GPIOA.MODER.access"]
    assert result.conflicts == ["NOPE.X.access"]
    assert effective.peripherals[0].registers[0].access == "read-only"


def test_batch_and_move_commands():
    from svdstudio.application.commands import BatchAttrCommand, MoveCommand
    from svdstudio.domain.model import SvdRegister
    regs = [SvdRegister(name="A"), SvdRegister(name="B")]
    refreshed = []
    batch = BatchAttrCommand(regs, "access", "read-only", lambda: refreshed.append(1))
    batch.redo()
    assert [r.access for r in regs] == ["read-only", "read-only"]
    batch.undo()
    assert [r.access for r in regs] == ["", ""]
    move = MoveCommand(regs, regs[0], 1, lambda: refreshed.append(1))
    move.redo()
    assert [r.name for r in regs] == ["B", "A"]
    move.undo()
    assert [r.name for r in regs] == ["A", "B"]


def test_svd_defaults_materialized():
    from svdstudio.domain.svd_defaults import new_field, new_register
    reg = new_register("CR1", 0)
    assert (reg.access, reg.size, reg.reset_value, reg.reset_mask) == \
        ("read-write", 32, 0, 0xFFFFFFFF)
    assert reg.protection == "" and reg.read_action == ""
    field = new_field("EN", 0, 1, parent_access="read-only")
    assert (field.access, field.lsb, field.msb) == ("read-only", 0, 0)


def test_all_icons_valid():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from svdstudio.ui.icons import validate_all
    assert validate_all() == []
    _ = app


def test_overlay_yaml_roundtrip(tmp_path):
    from svdstudio.domain import overlay_file as OF
    path = str(tmp_path / "ov.yaml")
    OF.save_overlay_file({"GPIOA.MODER.access": "read-only"}, path, {"v": 1})
    assert OF.load_overlay_file(path) == {"GPIOA.MODER.access": "read-only"}


def test_insert_delete_commands_are_undoable():
    items = []
    register = SvdRegister(name="TEST")
    refreshed = []
    insert = InsertCommand(items, register, 0, "Add TEST", lambda: refreshed.append("insert"))
    insert.redo()
    assert items == [register]
    insert.undo()
    assert items == []
    delete = DeleteCommand(items, register, "Delete TEST", lambda: refreshed.append("delete"))
    items.append(register)
    delete.redo()
    assert items == []
    delete.undo()
    assert items == [register]
    assert refreshed == ["insert", "insert", "delete", "delete"]
