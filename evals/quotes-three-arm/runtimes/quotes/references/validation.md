# Engine validation for 1.0.0

Run in `scripts/` using an interpreter with `requirements.txt` and optionally `requirements-mcp.txt` installed:

```bash
python -m unittest discover -s tests -v
```

The tests cover Python/JVM parsing, polyglot detection and conservative resolution, custom declarative languages, incremental freshness, installation conflicts, graph serialization, budgeted retrieval, and actual MCP stdio tool calls. MCP tests skip if its optional SDK is absent; a skipped test is not protocol evidence.

The engine covers complete JSON/text output budgets, overlapping source-span receipts, Unicode continuation, decoder-change invalidation, local metadata-only telemetry, explicit ignored-root discovery, and query-centered excerpts inside long declarations. The 1.0.0 CLI also tests a no-argument guide, explore budgets, named sessions, safe session paths, and stats without an index. Full executed test and distribution results are in the repository's root `VALIDATION.md`; Linux/Windows CI is defined separately. Heuristic parsing is not compiler semantics, and byte-payload comparisons are not measured agent billing savings. Known filenames avoid content probes during unchanged discovery; fallback text may be probed and reports inventory costs.

Source hash verification, graph snapshots, and analyzer/config fingerprints are separate freshness signals. A passing test suite does not make unresolved overloads, runtime dispatch, macros, generated code, or unsupported constructs resolved facts.
