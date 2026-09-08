# Exact archive caller lookup

`archive-callers` resolves an exact ID, unique exact name/qualname, or recorded Python module-qualified name and returns incoming calls in one command. Ambiguous and substring-only matches fail. Exact IDs take precedence. Existing incoming-neighbor rendering, byte budgets, pagination, path filtering and optional source hash verification are reused. Resolution adds a complete validated streaming pass, with archive identity/stat checks across the operation; it does not create SQLite.

On the unchanged frozen Django force_bytes archive, both `django.utils.encoding.force_bytes` and `force_bytes` returned exactly the same full packet as the exact-ID incoming calls query: 46 sites, scope django/*, text budget 64000, no context, no next page. One qualified query took 4.839 seconds; this is a single observation, not a performance comparison. Results are recorded in results.json.

Regression checks passed: ordinary and candidate-parser engine suites each 234 tests; root suite 53 tests. New coverage exercises gzip/XZ after source deletion, ambiguous/absent/partial names, exact IDs, Python module qualification, incoming packet equality across formats and offsets, path filtering, context equality, stale source rejection, actual CLI text byte limits and absence of consumer SQLite.

This change removes a required search/ID-copy step for unique exact identifiers. No new model trial was run, so actual token savings remain unproven. The existing skill entry point still documents search plus exact-ID neighbors; the archive reference documents the convenience command. Generic JVM inference and conservative coverage losses remain unresolved.

Fresh wheel and ZIP distribution verification also passed; see distribution.txt.
