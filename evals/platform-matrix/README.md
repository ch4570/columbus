# Hosted platform validation of graph/evidence changes

2026-09-08 KST. [Final CI run 34136986940](https://github.com/ch4570/columbus/actions/runs/34136986940) passed all six jobs at commit `87f5be009d11f6c3d1595171ab21a495050282bf` on branch `fix/ast-graph-evidence`.

| Platform | Python 3.11 | Python 3.14 |
| --- | --- | --- |
| Ubuntu | passed | passed |
| macOS | passed | passed |
| Windows | passed | passed |

Each job ran the root and engine tests, model-free observation harness tests and delivery checks, Python compilation, wheel/ZIP assembly, clean distribution verification and pre-commit integration. The extended distribution verifier checks compressed schema 3 and lazy unchanged sync, complete graph archives, source-free bounded queries, managed skill installation, source receipts, native hooks and relocated ZIP bootstrap. The pre-commit harness checks partial staging and deletion-only updates.

Existing platform exclusions remain explicit: the POSIX-only interpreter-alias test is excluded on Windows; the immutable historical RepoAtlas engine replay is excluded on Windows/Python 3.14. Current Columbus engine and distribution checks are not excluded for those reasons. Raw job/step outcomes are in [final.json](results/final.json).

The [initial run](https://github.com/ch4570/columbus/actions/runs/34136623601) passed four jobs and failed both Windows engine suites. The new archive parity test used a SQLite transaction context without closing the connection; Windows could not remove the temporary database (WinError 32). Explicit `closing(...)` now releases comparison connections in the test and verification script. [Failure excerpt](results/windows-cleanup.txt) and [initial outcomes](results/initial.json) are retained. The successful run tests the fix; the failed run was not rerun unchanged or hidden.

The current source was pushed to a dedicated validation branch. This is not a merged/released version or validation of the experimental patched Java grammar. The six jobs use the current runtime's pinned Java grammar, which retains known annotation recovery gaps. Actual model-token reduction remains unproven; the current-skill cohort's regressions are still recorded.

The latest [same-corpus index-layer measurement](../spring-core/results/final-storage/REPORT.md) uses current language extraction on both sides: fresh storage decreased 199,913,472 → 106,995,712 bytes, and unchanged-sync median decreased 1.0346 → 0.5016 seconds. Search/graph parity passed. One-file edit latency did not improve materially and still globally relinks; no proportional-update or model-token claim follows from these measurements.

[Windows test counts](results/windows-test-counts.json) confirm 190/190 current engine tests in both versions. Windows 3.11 ran 49 root tests with one POSIX exclusion and all 13 observation tests; Windows 3.14 had the same root exclusion and one historical-replay exclusion among its 13 observation tests. Exclusions are not counted as passing tests.
