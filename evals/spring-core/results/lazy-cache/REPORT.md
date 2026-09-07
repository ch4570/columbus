# Issue #6: lazy parse-cache validation

2026-09-08 KST. This is one completed optimization, not closure of issue #6 or the overall AST/agent efficiency goal.

Unchanged sync previously selected every cached parse body and decoded every JSON document even when no graph relink was necessary. It now reads file hashes/stat metadata first, loads cached facts only for a relink, and preserves snapshot diagnostics and reference counts. Strict parse validation still rejects an incomplete unchanged snapshot. Changed content, configuration, analyzer identity and deletions retain the existing atomic relink path. `refresh.cached_parses_loaded` exposes the work performed.

Same spring-core commit, 1,166 files / 7,120,331 indexed bytes, five in-process fast refreshes per implementation:

| Measurement | Before | After |
| --- | ---: | ---: |
| Median unchanged refresh | 0.9246 s | 0.5128 s |
| SQLite size | 199,421,952 bytes | unchanged schema/data |

Observed latency reduction: 44.5%. OS caches were not flushed; baseline ran first, and shared host load was uncontrolled. These are API timings, not CLI startup timings or model token measurements. Bounded default graph export equality before/after refresh passed. No storage reduction is claimed. Raw runs, source revision and modified engine SHA-256 are in [summary.json](summary.json).

Validation: engine suite 180 tests passed; root suite 49 tests passed; focused sync suite 17 passed (included in engine count). Compilation and pip check passed. The added regression rejects decoding any cached parse document during unchanged fast/full sync, checks diagnostics and unresolved counts, strict rejection, graph parity, and cache loading after repairing a broken file. Existing sync tests exercise stale-source and transaction rollback paths. Tests ran locally, not on the CI platform matrix.

This receipt predates compressed storage. The harness now excludes one-time migration; rerunning it measures the current engine rather than reconstructing the historical after revision. Run from the repository root with the development environment installed:

```sh
.venv/bin/python evals/spring-core/measure_lazy_cache.py /path/to/spring-framework/spring-core 4d55a34
```

Remaining work: index amplification and one-file edit latency with search parity (#6); JVM false targets and completeness response metadata (#8); annotated varargs grammar evaluation and independently reviewed relationship corpus (#4); final distribution/skill checks and task-level token evaluation. Smaller response bytes alone do not establish lower model token usage. These issues remain open.
