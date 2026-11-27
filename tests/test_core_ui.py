"""Regression coverage for the normal Qt authoring and profile workflows."""
from pathlib import Path
from zipfile import ZipFile

import pytest
from PySide6.QtCore import QElapsedTimer, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox, QTableView

from svdstudio.domain.diff import diff_devices
from svdstudio.infrastructure.svd_parser import parse_file
from svdstudio.infrastructure.tmk_registers import load_tmk_register_profile
from svdstudio.ui import main_window
from svdstudio.ui.create_dialogs import CoreRegisterDialog, FieldDialog

FIXTURE = Path(__file__).with_name("fixtures") / "simple.svd"


@pytest.fixture
def window(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    settings = tmp_path / "settings.ini"
    monkeypatch.setattr(main_window, "QSettings", lambda *_: QSettings(
        str(settings), QSettings.Format.IniFormat
    ))
    app = QApplication.instance() or QApplication([])
    editor = main_window.MainWindow()
    editor.show()
    editor.open(FIXTURE)
    timer = QElapsedTimer()
    timer.start()
    while editor.state.device is None and timer.elapsed() < 5000:
        QTest.qWait(20)
    assert editor.state.device is not None
    yield editor
    editor.state.dirty = False
    editor.close()
    app.processEvents()


def edit_property(window, attribute, text):
    for row in range(window.props.rowCount()):
        item = window.props.item(row, 1)
        if item.data(Qt.ItemDataRole.UserRole) == attribute:
            item.setText(text)
            return
    pytest.fail(f"Missing property row {attribute}")


def test_edit_cpu_and_core_registers_with_undo_and_save(window, monkeypatch, tmp_path):
    device = window.state.device
    assert window.model.source_index_for(device.cpu).isValid()
    window._select_object(device.cpu)
    edit_property(window, "name", "CM4")
    edit_property(window, "revision", "r0p1")
    edit_property(window, "endian", "little")
    edit_property(window, "nvic_prio_bits", "0")
    edit_property(window, "vendor_systick_config", "false")
    window.undo.undo()
    assert "vendorSystickConfig" not in device.cpu.meta.present
    window.undo.redo()
    assert "vendorSystickConfig" in device.cpu.meta.present

    first_peripheral = device.peripherals[0]
    window._select_object(first_peripheral.registers[0])
    assert window.findChild(QTableView, "registerMapView").model().rowCount() > 0
    assert window._select_by_path(f"{device.name}.coreRegisters")

    monkeypatch.setattr(QInputDialog, "getText", lambda *_: ("TEST_CPU", True))
    window.add_selected_child()
    group, = device.core_register_groups

    def create_register(dialog):
        dialog.name.setText("TR")
        return dialog.DialogCode.Accepted

    monkeypatch.setattr(CoreRegisterDialog, "exec", create_register)
    window.add_selected_child()
    register, = group.registers
    assert window.bitview.reg is register
    assert window.bitview._reg_address is None
    assert window.findChild(QTableView, "registerMapView").model().rowCount() == 0

    def create_field(dialog):
        dialog.name.setText("EN")
        dialog.access.setCurrentText("RW")
        return dialog.DialogCode.Accepted

    monkeypatch.setattr(FieldDialog, "exec", create_field)
    window.add_selected_child()
    field, = register.fields
    assert field.access == "RW"
    edit_property(window, "bit_offset", "7")
    assert (field.lsb, field.msb) == (7, 7)
    window.undo.undo()
    assert (field.lsb, field.msb) == (0, 0)
    window.undo.redo()
    assert (field.lsb, field.msb) == (7, 7)

    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Yes)
    window.delete_selected()
    assert not register.fields
    window.undo.undo()
    assert register.fields == [field]

    output = tmp_path / "edited.svd"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_: (str(output), ""))
    window.save_as()
    edited = parse_file(output)
    assert edited.cpu.nvic_prio_bits == 0
    assert "nvicPrioBits" in edited.cpu.meta.present
    assert edited.cpu.vendor_systick_config is False
    assert "vendorSystickConfig" in edited.cpu.meta.present
    saved_field = edited.core_register_groups[0].registers[0].fields[0]
    assert (saved_field.name, saved_field.access, saved_field.bit_offset) == ("EN", "RW", 7)
    assert not diff_devices(device, edited).entries


def test_import_jar_merge_and_export_selected_profile(window, monkeypatch, tmp_path):
    jar = tmp_path / "profiles.jar"
    with ZipFile(jar, "w") as archive:
        archive.writestr(
            "cn/com/tmkstudio/debug/registers/c28xx.xml",
            '<cpu id="TMS320C28XX"><register id="ST0" width="16">'
            '<bitfield id="OV" begin="1" end="1" access="RW"/></register></cpu>',
        )
        archive.writestr(
            "cn/com/tmkstudio/debug/registers/c28xx-fpu.xml",
            '<cpu id="TMK_SIMULATOR_FPU"><register id="R0H" width="32"/></cpu>',
        )
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_: (str(jar), ""))
    window.import_core_profiles()
    device = window.state.device
    cpu, fpu = device.core_register_groups
    assert [cpu.name, fpu.name] == ["TMS320C28XX", "TMK_SIMULATOR_FPU"]
    assert window._selected_node.obj is cpu
    window.undo.undo()
    assert device.core_register_groups == []
    window.undo.redo()
    assert device.core_register_groups == [cpu, fpu]

    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.No)
    window.import_core_profiles()
    assert device.core_register_groups[0] is cpu

    destination = tmp_path / "c28xx-fpu.xml"

    def select_destination(_window, _title, suggested_name, _filter):
        assert suggested_name == destination.name
        return str(destination), ""

    monkeypatch.setattr(QFileDialog, "getSaveFileName", select_destination)
    window._select_object(fpu.registers[0])
    window.export_core_profile()
    exported = load_tmk_register_profile(destination)
    assert exported.name == fpu.name
    assert exported.registers[0].name == "R0H"


def test_background_open_preserves_intervening_edits_on_cancel(window, monkeypatch):
    from svdstudio.application.project import ProjectState
    from svdstudio.domain.model import SvdDevice
    from svdstudio.ui import load_worker

    callbacks = []
    monkeypatch.setattr(load_worker, "load_svd_async", lambda _w, _p, done: callbacks.append(done))
    original = window.state.device
    window.open("other.svd")
    window._select_object(original.cpu)
    edit_property(window, "name", "CM4")

    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Cancel)
    callbacks[0](ProjectState(SvdDevice(name="OTHER"), "other.svd"), [], None)

    assert window.state.device is original
    assert original.cpu.name == "CM4"
