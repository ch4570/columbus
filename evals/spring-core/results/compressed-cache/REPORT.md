# Issue #6: compressed parse cache and lazy refresh

2026-09-08 KST. Local macOS / Python 3.11 validation against Spring commit `4c8c6409a27a62ab163d3b6196ad862b7c835440`. Baseline: `4d55a3438f375aada7ca063aa3dba434bc1a3725`. Engine SHA-256 and raw measurements: [summary.json](summary.json).

Schema 3 stores parse-cache JSON losslessly with standard-library zlib. Search rows, graph relationships and source verification retain their existing representation. Unchanged sync reads metadata and persisted coverage counts without loading cached parse bodies. Changed snapshots still globally relink. Schema 2 remains readable and is rebuilt atomically on the next sync; the rollback regression proves failed migration retains the old snapshot.

| Same corpus: 1,166 files, 7,120,331 source bytes | Before | After |
| --- | ---: | ---: |
| Fresh database physical bytes | 199,421,952 | 109,953,024 |
| Parse-cache table allocated bytes | 95,227,904 | 5,758,976 |
| Unchanged API sync, median of five | 0.9950 s | 0.5521 s |
| One-file edit, one observation | 3.7154 s | 3.8310 s |
| Cold index, one observation | 6.2783 s | 6.0265 s |

Physical size decreased 44.9%. OS caches were not flushed, baseline ran first, host load was uncontrolled. Times exclude CLI startup. Cold/edit measurements are single observations, not robust performance estimates. Database size is measured after initial connection closure; table allocations and physical size are reported separately. An in-place upgraded database retains free pages until SQLite VACUUM or a fresh DB is used.

All symbol rows and all edge rows were hashed in stable SQL order, including metadata/evidence: equality passed for both original and edited snapshots. Restoring source restored those facts in both engines. Twelve identifier/body queries, up to 50 hits each, retained exact hit objects and BM25 ranking. This checks all stored graph facts and the listed search workload; it does not establish JVM semantic correctness. Source-edit bytes were restored in finally; the original file SHA-256 is retained.

Validation: 181 engine tests and 49 root tests passed; compilation and pip check passed; skill quick_validate passed. Added regressions cover unchanged fast/full cache avoidance, preserved diagnostics/unresolved counts, strict rejection, changed-file relinking, compression round-trip through source lookup, schema 2 reads and failed/successful migration. Existing tests cover stale source, concurrent edits, rollback, JSONL trees and bounded retrieval. A built wheel installed outside the checkout, with PYTHONPATH removed and paths containing spaces, created a compressed index and returned a labelled JSONL AST tree. This smoke test used system site packages for dependencies; it is not the full clean wheel/ZIP distribution matrix. No hosted platform run has been performed for these changes.

Reproduce from repository root:

```sh
.venv/bin/python evals/spring-core/measure_storage.py /path/to/spring-framework/spring-core 4d55a34
```

This reduces storage but the index remains about 15.4 times source bytes. FTS source duplication and symbol/edge storage remain substantial. Issue #6 stays open pending further storage/output work and full release validation. Issues #4/#8 and actual agent-token evaluation remain in the overall goal. Model token reduction is not inferred from disk size or API latency.
