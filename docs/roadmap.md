# Roadmap

- Phase 0: 调研 + ADR ✅ (this repo state)
- Phase 1: Vertical Slice — open SVD, tree, property, bitview, save, schema check ✅ target
- Phase 2: CRUD + undo/redo + search (single-object Add/Duplicate/Delete + property edit commands done; batch ops, path/address lookup NOT IMPLEMENTED)
- Phase 3: Semantic validation (basic rules done; autofix preview NOT IMPLEMENTED)
- Phase 4: Diff (NOT IMPLEMENTED — stub `domain/diff.py`)
- Phase 5: Overlay/Effective (pure helpers done; YAML overlay file format NOT IMPLEMENTED)
- Phase 5: Tabular import foundation ✅ CSV/TSV importer, XLSX optional adapter, mapping plan, CLI preview/import; GUI preview, multi-sheet profiles, AI/MCP adapter NOT IMPLEMENTED
- Phase 5.5: Workbench UI ✅ Designer layout, adaptive splitters, menu/actions, QSS theme layer, readable bit-layout legend; final icon system, dock persistence, light/high-contrast themes NOT IMPLEMENTED
- Phase 5.1: Designer UI foundation ✅ `.ui` adaptive workspace, named placeholders, QSS theme layer, optional qdarkstyle adapter; polished Bit View and full visual system NOT IMPLEMENTED
- Phase 6+: IRQ/Pin/Clock/Pack/Debug — Domain placeholders only, NOT IMPLEMENTED
