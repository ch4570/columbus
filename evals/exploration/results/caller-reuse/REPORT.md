# Excerpt-reuse guidance: no savings demonstrated

Both fresh answers pass exact caller-set, contiguous citation and source-based semantic review. Source and requested settings match; no timeout, failed command or selective rerun occurred. The revised skill explicitly permits citing hash-verified excerpts and batching remaining checks. The model nevertheless read source, searched the graph, called callers, and reread source across separate commands.

| Measure | Baseline | Columbus |
| --- | ---: | ---: |
| Input tokens | 80,313 | 134,155 |
| Cached input subset | 56,832 | 87,424 |
| Uncached input | 23,481 | 46,731 |
| Output tokens | 3,476 | 4,055 |
| Commands | 4 | 12 |
| Command output bytes | 52,612 | 48,185 |
| Elapsed seconds | 123.363 | 145.165 |

Total input increased **67.04%**, uncached input **99.02%**, output **16.66%**, and elapsed time **17.67%**. A small 8.41% command-output reduction does not establish model-token or billing savings. Graph commands were at positions 3 and 4; both succeeded. The baseline batched its source inspection into fewer commands.

[Controlled evidence](controlled.json) retains both answers, usage, prompts/invocations, command/output hashes, source/engine/skill manifests and grades. Raw events and snapshots remain under `.omx/observations/caller-reuse/`. Both semantic reviews found correct direct ownership and imports, including archive.emit rather than archive.

The sequence of caller pilots is development feedback on one small task, not independent validation of a general efficiency claim. Stop further tuning against this task. The next evaluation should predeclare a separate continuous-work scenario where the same agent retains earlier source and receipts can suppress redundant ranges, while still evaluating accuracy and full usage. Graph correctness, compact archives and supported-platform installation remain useful verified capabilities; overall actual-token savings remain unproven.
