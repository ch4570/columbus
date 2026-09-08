# Exact archive caller lookup

`archive-callers` resolves an exact ID, unique exact name/qualname, or recorded Python module-qualified name and returns incoming calls in one command. Ambiguous and substring-only matches fail. Exact IDs take precedence. Existing incoming-neighbor rendering, byte budgets, pagination, path filtering and optional source hash verification are reused. Resolution adds a complete validated streaming pass, with archive identity/stat checks across the operation; it does not create SQLite.

On the unchanged frozen Django force_bytes archive, both `django.utils.encoding.force_bytes` and `force_bytes` returned exactly the same full packet as the exact-ID incoming calls query: 46 sites, scope django/*, text budget 64000, no context, no next page. One qualified query took 4.839 seconds; this is a single observation, not a performance comparison. Results are recorded in results.json.

Regression checks passed: ordinary and candidate-parser engine suites each 234 tests; root suite 53 tests. New coverage exercises gzip/XZ after source deletion, ambiguous/absent/partial names, exact IDs, Python module qualification, incoming packet equality across formats and offsets, path filtering, context equality, stale source rejection, actual CLI text byte limits and absence of consumer SQLite.

This change removes a required search/ID-copy step for unique exact identifiers. No new model trial was run, so actual token savings remain unproven. Generic JVM inference and conservative coverage losses remain unresolved.

Fresh wheel and ZIP distribution verification also passed; see distribution.txt.

## Skill entry point and full context pagination

The saved-graph entry point now uses archive-callers directly, retaining archive-search as the ambiguity/absence fallback. Source freshness, scope, exact cursors and additional source inspection remain explicit. Skill validation passed; root suite passed again (53 tests).

`verify_context.py /tmp/columbus-archive-force-bytes-trial OUTPUT` applies the documented 20-line radius and 12000-byte text budget with the task scope django/*. All six pages returned 46 sites across 37 owners in 17 files, exactly matching the independent frozen oracle. Every returned excerpt was checked against hash-verified source, including same-line call multiplicity. Page bytes were 11699, 11358, 9882, 11412, 11839 and 10067; offsets were 0, 6, 14, 22, 29, 36, then null. The complete verifier result equals the earlier exact-ID-neighbors context result. No archive changes or consumer SQLite were found. This verifies command behavior; it is not an independent model behavior or usage trial.

Remote distribution run 34175816099 at 9dda7d0 had passed four Linux/macOS jobs while two Windows jobs were still running at the retained observation; no all-platform completion claim is made here.
