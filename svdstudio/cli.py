"""svdstudio CLI: validate, info, and tabular import."""
from __future__ import annotations

import argparse

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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="svdstudio")
    sub = parser.add_subparsers(dest="cmd", required=True)

    validate = sub.add_parser("validate")
    validate.add_argument("svd")

    info = sub.add_parser("info")
    info.add_argument("svd")

    table = sub.add_parser("import-table", help="Import CSV/TSV/XLSX into an SVD")
    table.add_argument("input", help="CSV, TSV, XLSX or XLSM file")
    table.add_argument("output", help="Output SVD path")
    table.add_argument("--device", required=True, help="Device name")
    table.add_argument("--vendor", default="", help="Vendor name")
    table.add_argument("--mapping", default="", help="JSON mapping plan")
    table.add_argument("--sheet", default="", help="XLSX worksheet name")
    table.add_argument("--dry-run", action="store_true", help="Validate and preview without writing")

    args = parser.parse_args(argv)
    if args.cmd == "validate":
        _, issues = P.open_svd(args.svd)
        for issue in issues:
            print(f"[{issue.severity.value.upper()}] {issue.rule_id} {issue.path}: {issue.message}")
        return 1 if any(issue.severity.value == "error" for issue in issues) else 0
    if args.cmd == "info":
        state, _ = P.open_svd(args.svd)
        print(f"device={state.device.name} peripherals={len(state.device.peripherals)}")
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
