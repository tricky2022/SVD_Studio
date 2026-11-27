"""svdstudio CLI: validate, info, and tabular import."""
from __future__ import annotations

import argparse
import json
import sys

from svdstudio import __version__
from svdstudio.application import project as P
from svdstudio.application.tabular_import import import_file
from svdstudio.domain.model import iter_registers
from svdstudio.validators import Issue, Severity
from svdstudio.validators.validate import core_register_issues


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
        return [Issue("XML-001", Severity.ERROR, path,
                      f"{type(error).__name__}: {error}")], []

    schema_issues: list = []
    if allow_discovery:
        try:
            resolved = X.discover_schema(path, schema)
        except X.SchemaUnavailable as error:
            schema_issues = [Issue("XSD-001", Severity.ERROR, schema, str(error), source=schema)]
        else:
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


def _tmk_core(args) -> int:
    from svdstudio.infrastructure import tmk_registers as tmk

    try:
        state, _ = P.open_svd(args.svd)
        groups = state.device.core_register_groups
        if args.cmd == "export-tmk-core":
            matches = [group for group in groups if group.name == args.group]
            if len(matches) != 1:
                raise ValueError(f"Expected one core register group with ID {args.group!r}")
            tmk.save_tmk_register_profile(matches[0], args.output)
        else:
            incoming = (tmk.load_tmk_register_profiles_from_jar(args.jar) if args.jar else
                        [tmk.load_tmk_register_profile(path) for path in args.xml])
            known = {group.name: index for index, group in enumerate(groups)}
            for group in incoming:
                if group.name in known:
                    if not args.replace:
                        raise ValueError(f"Group {group.name!r} already exists. Use --replace to update it.")
                    groups[known[group.name]] = group
                else:
                    known[group.name] = len(groups)
                    groups.append(group)
            issues = core_register_issues(state.device)
            if issues:
                for issue in issues:
                    print(issue.to_line(), file=sys.stderr)
                return 1
            P.save_svd(state, args.output)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"written={args.output}")
    return 0


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

    core = sub.add_parser("import-tmk-core", help="Import TMK CPU/FPU profiles into an SVD")
    core.add_argument("svd", help="Input SVD")
    core.add_argument("output", help="Output SVD")
    profiles = core.add_mutually_exclusive_group(required=True)
    profiles.add_argument("--xml", nargs="+", help="One or more TMK CPU/FPU profile XML files")
    profiles.add_argument("--jar", help="TMKStudioIDE debug core plugin JAR")
    core.add_argument("--replace", action="store_true", help="Replace an existing group by its ID")

    export = sub.add_parser("export-tmk-core", help="Export one SVD group as TMK profile XML")
    export.add_argument("svd")
    export.add_argument("group", help="Core register group ID")
    export.add_argument("output", help="Output TMK profile XML")

    args = parser.parse_args(argv)

    if args.cmd in ("import-tmk-core", "export-tmk-core"):
        return _tmk_core(args)

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
        registers = [register for peripheral in device.peripherals
                     for register in iter_registers(peripheral)]
        fields = sum(len(register.fields) for register in registers)
        if args.json:
            summary = {
                "path": args.svd,
                "device": device.name,
                "vendor": device.vendor,
                "peripherals": len(device.peripherals),
                "registers": len(registers),
                "fields": fields,
                "core_register_groups": [
                    {"id": group.name, "registers": len(group.registers),
                     "fields": sum(len(register.fields) for register in group.registers)}
                    for group in device.core_register_groups
                ],
            }
            print(json.dumps(summary, indent=2, ensure_ascii=False))
            return 0
        print(f"device={device.name} vendor={device.vendor} "
              f"peripherals={len(device.peripherals)} registers={len(registers)} fields={fields}")
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
