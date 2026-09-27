# Contributing to SVD Studio

Thanks for contributing. SVD Studio is an engineering tool, so correctness and round-trip fidelity matter as much as UI polish.

## Before opening a pull request

```powershell
python -m pytest -q
python -m ruff check svdstudio tests
```

For UI changes also run the offscreen startup check used by the maintainers:

```powershell
$env:QT_QPA_PLATFORM="offscreen"
python -c "from PySide6.QtWidgets import QApplication; from svdstudio.ui.main_window import MainWindow; app=QApplication([]); MainWindow(); print('UI OK')"
```

## Coding rules

- Keep domain code free of Qt and XML-library imports.
- Put user-visible mutations behind an application command so undo/redo remains correct.
- Add a regression test for parser, serializer, validation, diff, overlay or default-value changes.
- Keep UI strings in the bilingual string table when practical; SVD content itself must never be translated.
- Avoid comments that narrate obvious code. Document constraints and non-obvious decisions.
- Do not commit generated `build/`, `dist/`, `.pytest_cache/`, virtual environments or secrets.

## Pull requests

Describe:

1. What user problem is solved.
2. Which domain/application/UI layers changed.
3. How the change was tested.
4. Any CMSIS-SVD compatibility or migration implications.

Screenshots are welcome for workbench changes, especially for both light and dark themes.
