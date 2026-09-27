# SVD Studio — Architecture (Phase 0/1)

## 1. Layering (mandatory)

```
ui/  (PySide6 Widgets, Model/View only)
  -> application/  (use-cases, QUndoCommand factories, services)
    -> domain/  (pure Python dataclasses, NO Qt, NO lxml)
      <- infrastructure/  (SVD parse adapter over cmsis-svd + lxml)
      <- serializers/     (domain -> SVD XML via lxml)
      <- validators/      (schema + semantic, pure, return Issue[])
      <- diff/ overlay/ generators/  (Phase 4+, stubs)
```

Rules: UI never touches XML. Domain never imports PySide6/lxml.
`cmsis-svd` is used for research/reference; our own parser is source of truth
for round-trip fidelity (cmsis-svd drops unknown/ordering info). `svdtools`
is NOT a dependency yet — future patch/derive via adapter. SVDConv is an
external subprocess validator (optional, configured path).

## 2. Internal model is a SUPERSET of SVD

Every node has `meta: NodeMeta` (source file, origin, provenance flags,
notes, tags) which is NEVER serialized to SVD. SVD fields are kept 1:1
including dim/dimIndex/derivedFrom/alternate*/protection/readAction/
modifiedWriteValues/writeConstraint/enumeratedValues.

Provenance enum: ORIGINAL | MODIFIED | INHERITED | DERIVED | GENERATED | CONFLICT.

## 3. Effective model (Phase 5 stub)

`domain/effective.py` exposes `expand_dim()` and `resolve_derived_from()`
as pure functions producing generated nodes flagged GENERATED/DERIVED.
GUI toggle raw vs effective (Phase 2+). Overlay apply = pure merge
`overlay/merge.py` (stub now).

## 4. Project layout (.svdstudio)

```
project.svdproj (json) + vendor/ + overlays/ + exports/ + reports/
```
Phase 1: single-file open/save SVD directly; project file support minimal.

## 5. Validation levels

L1 well-formed (lxml), L2 XSD (optional local xsd, graceful skip),
L3 semantic (pure domain checks, always run). Issues carry
rule_id/severity/path/message/suggestion/can_autofix.

## 6. Tabular Import and AI integration boundary

Large DSP/SoC descriptions should not require hand-writing XML. SVD Studio now has a deterministic tabular import service:

```text
CSV/TSV/XLSX
  -> normalized rows
  -> JSON mapping plan
  -> ImportResult + row diagnostics
  -> preview / approval
  -> domain model
  -> SVD serializer
```

The importer currently accepts flat rows with peripheral, base address, register, offset, access, reset, field, bit offset/width, and enumeration columns. It also accepts column aliases and an explicit JSON mapping plan. CSV/TSV are dependency-free; XLSX uses the optional `excel` extra (`pip install -e ".[excel]"`).

AI integration is deliberately outside the domain and XML layers. A future local/remote AI adapter may inspect headers and sample rows and propose a mapping plan, but SVD Studio validates the plan, produces a preview, reports conflicts, and only then applies it. The first automation endpoint is the CLI, so an AI agent can invoke `import-table --dry-run`, inspect diagnostics, then invoke the approved import. A future MCP/HTTP/PyCharm adapter should call this same application service rather than manipulate files directly.

## 7. UI composition and theme boundary

The main workspace layout is authored in `resources/ui/main_window.ui` and loaded at runtime with `QUiLoader`. Python owns only wiring: models, commands, services, signals, and lifecycle. Custom widgets such as `PropertyEditor` and `BitView` are inserted into named Designer placeholders. This keeps layout iteration in Qt Designer and prevents a monolithic Python window class. The Bit View is a composite widget: a compact bit canvas is paired with a field legend table, so narrow fields remain readable without requiring every label to fit inside a bit cell.

`resources/styles/base.qss` contains the project layer. `svdstudio.ui.theme.apply_theme()` optionally prepends qdarkstyle when that extra is installed, then applies the project overrides. Theme policy is intentionally independent from domain/application code so future light/dark/high-contrast themes can be selected without touching SVD logic.

## 8. Decisions

See docs/decisions/ADR-*.md.
