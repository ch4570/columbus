# Source/call-site cohort: completed, rejected

All 18 frozen executions and independent reviews are retained. **0/6 primary pairs and 0/6 secondary pairs pass; the experiment is not accepted.** Candidate total input and output are not both lower in any primary pair; output is higher in all six. Actual source-plus-call delivery occurred in 3/6 candidate runs, but delivery is not a substitute for complete answers or lower usage. No main merge, tag, release or cost-saving claim is authorized by this result.

## Complete evidence

- Frozen experiment: commit `28bfa454044f88e2cc0096f509ae316a4676f209`, tree `f928f15d855852b25acd996b899b159e958abf46`; all **449** frozen inputs verified.
- Input inventory SHA256: `69f196d7db2fac0248805878f294966774346028dee725f439707702d60c2fa6`.
- [Full collector report](retained/collector-report.json), SHA256 `d1f5608c712cf503f9b00f1c97520ea94e58d65b199bd42287756a2551fcbf22`: 18/18 verified, pending 0, errors `[]`, all three complete fixed orders pass. Collector exit 1 is the expected acceptance rejection, not an integrity failure.
- [Lossless retention manifest](retained/RETENTION.json), SHA256 `b49ec88ad60904525a9051dd5f4e3f2718de6ad406e1a9df8eb2f18e429b6f9d`: **198 payload files**, complete cohort, issues `[]`. Capture and a separate standalone verification both passed. Every raw trial artifact and all 18 hash-bound reviews remain present; JSONL has both original-byte and lossless gzip hashes.
- All original runner handles exited 0 and every model process returned 0 without timeout. [Owner handle confirmation](audit/runner-handle-closure.json) was recorded after direct tool-session termination, not inferred from absent files. No retries, resumes, resampling, omitted failures, answer changes or rubric changes occurred.
- Exact frozen-head [PR CI](https://github.com/ch4570/columbus/actions/runs/34279963791) and [push CI](https://github.com/ch4570/columbus/actions/runs/34279962669) passed all 12 jobs before launch; [complete receipt](audit/prelaunch-ci.json). The post-run retention utility was separately tested before PR #23 merged; [premerge CI receipt](audit/pr23-premerge-ci.json). These audit files are post-run evidence, not new model inputs.

The original immutable checkout and original observations remain unchanged and available. Frozen source ZIPs, archives, runtimes, rubrics and protocol files are linked by exact commit/path/hash rather than duplicated in retention. Original absolute invocation paths remain recorded; this is not a portable model replayer. The manifest hash above is an external authenticity anchor in addition to internal hash consistency.

## All matched comparisons

Deltas are candidate minus comparator, using actual total input and output (including recorded reasoning output). Cached input is a subset of total input and is never added a second time.

| Language / repeat | vs baseline input | vs baseline output | vs control input | vs control output |
| --- | ---: | ---: | ---: | ---: |
| java / 1 | -53,737 | +1,163 | -119,693 | -60 |
| java / 2 | +17,912 | +2,155 | +14,475 | +394 |
| kotlin / 1 | +96,049 | +450 | -99,610 | -1,808 |
| kotlin / 2 | -65,549 | +3,375 | -63,410 | +598 |
| javascript / 1 | +295,593 | +5,149 | +182,751 | +3,931 |
| javascript / 2 | +134,693 | +3,668 | +92,590 | -906 |

Two secondary pairs have lower input and output numerically, but neither satisfies the complete prespecified quality/graph-utility gate. Secondary comparisons, aggregates, cached-input-only changes and serialized-byte estimates cannot replace the six primary pairs.

## Every scheduled run

Citation and execution columns are the frozen reviewed gates; execution includes compliance, not merely a zero process exit. Clause counts do not substitute for all five requested findings. Graph means actual delivered, source-reviewed stored relationships, not a graph query alone.

| Run | Input | Output | Semantic clauses | Citation | Execution | Graph |
| --- | ---: | ---: | ---: | --- | --- | --- |
| java/baseline/1 | 197,731 | 9,764 | 17/18 | pass | pass | no |
| java/baseline/2 | 201,065 | 10,424 | 16/18 | pass | pass | no |
| java/control/1 | 263,687 | 10,987 | 18/18 | pass | pass | no |
| java/control/2 | 204,502 | 12,185 | 16/18 | pass | pass | no |
| java/candidate/1 | 143,994 | 10,927 | 17/18 | pass | pass | no |
| java/candidate/2 | 218,977 | 12,579 | 16/18 | pass | pass | yes |
| kotlin/baseline/1 | 150,174 | 11,117 | 19/19 | FAIL | pass | no |
| kotlin/baseline/2 | 304,165 | 10,383 | 18/19 | pass | pass | no |
| kotlin/control/1 | 345,833 | 13,375 | 19/19 | pass | pass | no |
| kotlin/control/2 | 302,026 | 13,160 | 19/19 | pass | pass | no |
| kotlin/candidate/1 | 246,223 | 11,567 | 19/19 | pass | pass | yes |
| kotlin/candidate/2 | 238,616 | 13,758 | 15/19 | FAIL | FAIL | no |
| javascript/baseline/1 | 104,362 | 11,655 | 18/19 | pass | pass | no |
| javascript/baseline/2 | 131,456 | 11,089 | 17/19 | FAIL | pass | no |
| javascript/control/1 | 217,204 | 12,873 | 18/19 | pass | pass | no |
| javascript/control/2 | 173,559 | 15,663 | 18/19 | pass | pass | no |
| javascript/candidate/1 | 399,955 | 16,804 | 19/19 | pass | pass | no |
| javascript/candidate/2 | 266,149 | 14,757 | 19/19 | pass | pass | yes |

There are 3 citation-failed runs, 11 semantic-failed runs and 1 execution-policy failure. Kotlin candidate-2 returned only three of five requested findings and omitted the mandatory supplied skill read. Other failures include specific constructor/context, placeholder-outcome and serialization omissions. All clause-by-clause reasons and original answers are retained. All six controls lack qualifying relationship delivery; issuing a query for an unresolved Kotlin handoff does not manufacture an edge.

## Descriptive totals, not the acceptance rule

| Arm (six runs) | Total input | Cached subset | Total output | Command items | Nonzero-exit items |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline | 1,088,953 | 831,744 | 64,432 | 61 | 4 |
| control | 1,506,811 | 1,262,592 | 78,243 | 87 | 6 |
| candidate | 1,513,914 | 1,272,064 | 80,392 | 109 | 7 |

Candidate versus baseline totals are **+39.02% input and +24.77% output**. The 17 nonzero-exit command items, including allowed no-match/ambiguous/budget failures, are preserved. These are shell-command items; a compound command can contain more than one tool invocation. No monetary price or token-causality allocation is inferred from these totals.

## Scope and interpretation

The requested model was `gpt-5.6-sol` with `xhigh` reasoning and a 1,200-second per-process timeout. Baseline is efficient ordinary read/search; control runtime is `402940994ba519a3a02a521ccfed55b73d310dbf`; candidate runtime is `382d92a780e933f43e267d12f41869c816eee3bb` with optional `archive-source --call-sites`. The balanced fixed schedule retains all six arm permutations, two repetitions across three languages. See the unchanged [plan](PLAN.md), [preflight](PREFLIGHT.md), [source provenance](sources.json) and [control capture history](CONTROL-CAPTURE.md). All 303 original model-free controls and their actual failed/successful raw outputs were preserved and replay-verified, not recaptured.

Java/Kotlin reuse previously measured operations, Axios is a reused corpus, and source/edge-informed selection is explicitly not held out. Historical graph exports were reused byte-for-byte with producer/source verification; fresh cold indexing/export times are null, not zero. Unresolved dispatch and heuristic gaps remain visible. The result is bounded evidence about this development comparison, not general proof that graphs cannot help.

Completed JavaScript traces show three distinct investigation costs: resolving ambiguous short names into exact IDs, reading helper bodies outside the selected declaration range, and reprinting already received source for further inspection or citation. Some extra reads are necessary: a complete source page plus stored call endpoints is not the callee implementation. These observations motivate prospective work but neither assign exact token causes nor establish savings. Any later batch-search change is outside the frozen candidate runtime and is not measured here.

The previous [18-run quote cohort](../quotes-three-arm/retained/collector-report.json) remains unchanged at 0/6 primary and 0/6 secondary. Retaining this rejected result does not regrade or replace any historical run.
