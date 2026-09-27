# SVD Studio

SVD Studio is a desktop CMSIS-SVD workbench for embedded engineers. It combines a high-density Qt workbench with a pure-Python domain model so device descriptions can be inspected, edited, validated, compared, overlaid and exported without hand-writing XML.

> Status: Beta / active development. The project is usable for real SVD exploration and authoring, but vendor-specific SVD extensions should be validated before production release.

## What it does

- Open, inspect and round-trip CMSIS-SVD files.
- Navigate Device → Peripheral → Cluster → Register → Field → Enumerated Values.
- Browse register maps with absolute addresses and reset values.
- Inspect bit layouts; double-click an unused bit to create a field.
- Edit properties with grouped sections and SVD-standard value choices.
- Create devices, peripherals, clusters, registers and fields with undo/redo.
- Validate XML and semantic rules with Problems navigation.
- Compare two devices with a tree diff.
- Apply and migrate YAML overlays for vendor updates.
- Preview/import CSV, TSV and XLSX register tables.
- Switch between Chinese and English UI and light/dark workbench themes.
- Build a Windows single-file executable with an application icon.

## Requirements

- Python 3.10 or newer
- PySide6 6.6 or newer
- Windows, Linux or macOS for the development build

## Development setup

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev,excel]"
```

Start the desktop application:

```powershell
.\.venv\Scripts\python -m svdstudio.app
```

Run the CLI:

```powershell
svdstudio validate path\to\device.svd
svdstudio info path\to\device.svd
svdstudio import-table registers.csv output.svd --device DSPDEV --dry-run
```

Run quality gates:

```powershell
python -m pytest -q
python -m ruff check svdstudio tests
```

## Windows release build

The repository includes the icon assets and a PyInstaller specification:

```powershell
.\build-exe.bat
```

The executable is written to `Releases/SVDStudio.exe`. Build output and temporary PyInstaller directories are ignored by Git.

## Architecture

```text
ui/            PySide6 workbench, model/view, dialogs and themes
application/   use cases, commands, import services and project lifecycle
domain/        pure SVD dataclasses, defaults, search, diff and overlay
infrastructure/parse adapters and external integrations
serializers/   domain → CMSIS-SVD XML
validators/    XML and semantic diagnostics
tests/         parser, serializer, editor and domain regression tests
```

The domain layer deliberately has no Qt or lxml imports. UI code never manipulates XML directly. This keeps the same SVD services usable from the desktop application, CLI and future automation adapters.

## Design principles

- Preserve source fidelity where possible; never silently discard vendor extensions.
- Make effective/inherited SVD values visible instead of inventing invalid XML defaults.
- Keep editing undoable and every mutation routed through an application command.
- Prefer explicit diagnostics over silent recovery.
- Treat the workbench as an IDE: keyboard shortcuts, context menus, stable selection, persistent layout and predictable navigation.

## Documentation

- [Architecture](docs/architecture.md)
- [Roadmap](docs/roadmap.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)

## License

SVD Studio is released under the [MIT License](LICENSE).
