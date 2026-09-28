"""svdstudio CLI: validate, info, and tabular import."""
from __future__ import annotations

import argparse
import json
import sys

from svdstudio import __version__
from svdstudio.application import project as P
from svdstudio.application.tabular_import import import_file


def _print_import_result(result) -> None:
    print(
        f"rows={result.rows_read} peripherals={result.peripherals_created} "
        f"registers={result.registers_created} fields={result.fields_created}"
    )
    for issue in result.issues:
        location = f"row {issue.row}" if issue.row else "input"
        suffix = f" [{issue.field}]" if issue.field else ""
        print(f"[{issue.severity.upper()}] {location}{suffix}: {issue.message}")


def _diagnose(path: str, schema: str = "", allow_discovery: bool = True) -> tuple[list, list]:
    """Run the full pipeline: parse, structural, semantic, optional schema.

    The schema stage only runs when a schema is given or one can be found
    locally; a missing schema is not reported as a problem.
    """
    from svdstudio.validators import xsd as X

    try:
        _state, issues = P.open_svd(path)
    except (OSError, ValueError) as error:
        from svdstudio.validators import Severity
        from svdstudio.validators.validate import Issue
        return [Issue("XML-001", Severity.ERROR, path,
                      f"{type(error).__name__}: {error}")], []

    schema_issues: list = []
    if allow_discovery:
        try:
            resolved = X.discover_schema(path, schema)
        except X.SchemaUnavailable:
            resolved = ""
        if resolved:
            schema_issues = X.validate_xsd(path, resolved)
    return issues, schema_issues


def _print_issues(issues) -> None:
    for issue in issues:
        print(issue.to_line() if hasattr(issue, "to_line")
              else f"[{issue.severity.value.upper()}] {issue.rule_id} {issue.path}: {issue.message}")
        if getattr(issue, "suggestion", ""):
            print(f"    hint: {issue.suggestion}")


def _exit_code(issues) -> int:
    return 1 if any(getattr(i.severity, "value", i.severity) == "error" for i in issues) else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="svdstudio",
        description=f"SVD Studio {__version__} — CMSIS-SVD workbench CLI")
    parser.add_argument("--version", action="version", version=f"SVD Studio {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    validate = sub.add_parser("validate", help="Validate an SVD (errors exit 1)")
    validate.add_argument("svd")
    validate.add_argument("--schema", default="",
                          help="Path to CMSIS-SVD.xsd (official schema check)")
    validate.add_argument("--no-schema", action="store_true",
                          help="Skip automatic schema discovery")
    validate.add_argument("--json", action="store_true", help="Machine-readable output")

    info = sub.add_parser("info", help="Print a device summary")
    info.add_argument("svd")
    info.add_argument("--json", action="store_true")

    doctor = sub.add_parser(
        "doctor", help="Full diagnosis report: line numbers, rules, hints")
    doctor.add_argument("svd")
    doctor.add_argument("--schema", default="")
    doctor.add_argument("--json", action="store_true")

    table = sub.add_parser("import-table", help="Import CSV/TSV/XLSX into an SVD")
    table.add_argument("input", help="CSV, TSV, XLSX or XLSM file")
    table.add_argument("output", help="Output SVD path")
    table.add_argument("--device", required=True, help="Device name")
    table.add_argument("--vendor", default="", help="Vendor name")
    table.add_argument("--mapping", default="", help="JSON mapping plan")
    table.add_argument("--sheet", default="", help="XLSX worksheet name")
    table.add_argument("--dry-run", action="store_true", help="Validate and preview without writing")

    args = parser.parse_args(argv)

    if args.cmd in ("validate", "doctor"):
        allow_discovery = not getattr(args, "no_schema", False)
        issues, schema_issues = _diagnose(args.svd, args.schema, allow_discovery)
        everything = list(issues) + list(schema_issues)
        if args.json:
            print(json.dumps([i.to_dict() for i in everything], indent=2, ensure_ascii=False))
        else:
            _print_issues(everything)
            errors = sum(1 for i in everything
                         if getattr(i.severity, "value", i.severity) == "error")
            warnings = sum(1 for i in everything
                           if getattr(i.severity, "value", i.severity) == "warning")
            print(f"\n{errors} error(s), {warnings} warning(s), {len(everything)} total")
        return _exit_code(everything)

    if args.cmd == "info":
        try:
            state, _ = P.open_svd(args.svd)
        except (OSError, ValueError) as error:
            print(f"error: {type(error).__name__}: {error}", file=sys.stderr)
            return 1
        device = state.device
        if args.json:
            from svdstudio import api
            print(json.dumps(api.summary(api.Session(path=args.svd, device=device)),
                             indent=2, ensure_ascii=False))
            return 0
        registers = sum(len(p.registers) for p in device.peripherals)
        fields = sum(len(r.fields) for p in device.peripherals for r in p.registers)
        print(f"device={device.name} vendor={device.vendor} "
              f"peripherals={len(device.peripherals)} registers={registers} fields={fields}")
        return 0

    if args.cmd == "import-table":
        result = import_file(args.input, args.device, args.mapping, args.sheet, args.vendor)
        _print_import_result(result)
        if not result.valid:
            return 1
        if not args.dry_run:
            P.save_svd(P.ProjectState(device=result.device, path=args.output, dirty=True))
            print(f"written={args.output}")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
