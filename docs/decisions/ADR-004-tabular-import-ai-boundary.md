# ADR-004: Tabular Import and AI Boundary

## Decision

SVD Studio introduces a deterministic `Tabular Import Pipeline` independent of Qt and AI:

```text
CSV/TSV/XLSX/JSON/other adapter
  -> normalized rows
  -> mapping plan
  -> ImportResult (domain objects + diagnostics)
  -> preview/approval
  -> SVD serializer
```

The importer owns validation and construction of the domain model. AI is an optional orchestration client that may inspect headers/sample rows and propose a versioned mapping plan, but it cannot directly edit XML or bypass the domain and validation layers.

## Mapping plan contract

A mapping plan is JSON with canonical keys such as `peripheral`, `base_address`, `register`, `address_offset`, `field`, `bit_offset`, `bit_width`, `enum`, and `enum_value`. Values point to source column names. The plan is reviewed before application and is suitable for local AI, remote AI, a future MCP adapter, or a PyCharm action.

## Safety rules

- AI output is untrusted input.
- Import always produces diagnostics and a preview before project mutation.
- No network/LLM dependency is included in the core package.
- Import can be run in CI through the CLI.
- Every approved import should become an undoable application command when connected to the GUI.

## Consequences

CSV/TSV support remains dependency-free. XLSX support is an optional `excel` extra using `openpyxl`. Vendor-specific layouts should be handled by mapping profiles or plugins, not by adding heuristics to the domain model.
