import json
from copy import deepcopy
from pathlib import Path

from svdstudio.cli import main
from svdstudio.domain.diff import diff_devices
from svdstudio.domain.model import CoreRegister, CoreRegisterGroup, SvdDevice, SvdField
from svdstudio.domain.search_utils import search
from svdstudio.validators.validate import core_register_issues
from svdstudio.validators.xsd import discover_schema, validate_xsd

FIXTURE = Path(__file__).with_name("fixtures") / "simple.svd"


def test_explicit_missing_schema_is_reported(tmp_path, capsys):
    missing = tmp_path / "missing.xsd"
    assert main(["validate", str(FIXTURE), "--schema", str(missing), "--json"]) == 1
    issues = json.loads(capsys.readouterr().out)
    assert any(issue["rule"] == "XSD-001" and issue["source"] == str(missing)
               for issue in issues)


def test_schema_validation_reports_source_location(tmp_path):
    schema = tmp_path / "CMSIS-SVD.xsd"
    schema.write_text(
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">'
        '<xs:element name="device" type="xs:positiveInteger"/>'
        '</xs:schema>',
        encoding="utf-8",
    )
    document = tmp_path / "test.svd"
    document.write_text("<device>42</device>", encoding="utf-8")
    assert discover_schema(str(document)) == str(schema)
    assert validate_xsd(str(document), str(schema)) == []
    document.write_text("\n<device>0</device>", encoding="utf-8")
    issue, = validate_xsd(str(document), str(schema))
    assert (issue.rule_id, issue.line, issue.source) == ("XSD-002", 2, str(document))


def test_tmk_core_cli_import_info_replace_and_export(tmp_path, capsys):
    profile = tmp_path / "input.xml"
    profile.write_text('<cpu id="CPU"><register id="R0" width="32"/></cpu>',
                       encoding="utf-8")
    unified = tmp_path / "unified.svd"
    import_command = ["import-tmk-core", str(FIXTURE), str(unified), "--xml", str(profile)]
    assert main(import_command) == 0
    capsys.readouterr()
    assert main(["info", str(unified), "--json"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["core_register_groups"] == [{"id": "CPU", "registers": 1, "fields": 0}]

    previous = unified.read_bytes()
    assert main(["import-tmk-core", str(unified), str(unified), "--xml", str(profile)]) == 1
    assert unified.read_bytes() == previous
    profile.write_text('<cpu id="CPU"><register id="R1" width="32"/></cpu>',
                       encoding="utf-8")
    assert main(["import-tmk-core", str(unified), str(unified),
                 "--xml", str(profile), "--replace"]) == 0
    output = tmp_path / "output.xml"
    assert main(["export-tmk-core", str(unified), "CPU", str(output)]) == 0
    assert 'id="R1"' in output.read_text(encoding="utf-8")


def test_core_groups_participate_in_search_diff_and_validation():
    old = SvdDevice(name="DSP")
    new = deepcopy(old)
    register = CoreRegister(name="ACC", size=32, fields=[
        SvdField(name="FLAG", bit_offset=31, bit_width=2),
    ])
    new.core_register_groups.append(CoreRegisterGroup(name="CPU", registers=[register]))
    hit, = search(new, "ACC.FLAG")
    assert (hit.path, hit.address) == ("coreRegisters.CPU.ACC.FLAG", None)
    assert "coreRegisters.CPU.ACC.FLAG" in {entry.path for entry in diff_devices(old, new).added}
    issue, = core_register_issues(new)
    assert issue.rule_id == "SVD-CORE-005"
