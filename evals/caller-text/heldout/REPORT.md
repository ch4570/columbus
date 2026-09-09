# Held-out read_stable caller observation

Both answers pass the exact caller-set/citation gate and manual explanation review, but Columbus increases input **77.71%**. This does not demonstrate token savings.

[Predeclared plan](PLAN.md), [independent target-edge oracle](oracle.json), [results, answers, prompts and invocations](results.json). Run baseline then Columbus, requested gpt-5.6-sol/xhigh, one ephemeral session each, 600-second timeout. Source is the unchanged c67b20a fixture; the frozen current engine/skill includes numbered caller text and the source-line fix. The initial preparation import-path assertion failed before any model trial; corrected preparation and both actual trials are retained without selective reruns.

| Runtime metric | Baseline | Columbus | Change |
| --- | ---: | ---: | ---: |
| input_tokens | 57,518 | 102,215 | +77.71% |
| cached_input_tokens | 50,048 | 75,648 | +51.15% |
| uncached_input_tokens | 7,470 | 26,567 | +255.65% |
| output_tokens | 2,048 | 3,824 | +86.72% |

Commands: 4 → 12. Recorded command-output bytes: 17,917 → 25,737. Elapsed time: 77.202s → 138.228s. Cached tokens are a subset of input; no billing inference is made. Requested model settings are not backend model attestations.

Columbus read the skill, then successfully used `callers read_stable --format text` as command two. It subsequently performed three rg searches and seven source reads, including three numbered rereads. There were no failed commands. Numbered evidence therefore did not prevent redundant source inspection on this target. Both answers identify refresh, status and _source; the independently reviewed five direct call sites and three owners match the graph exactly.

Post-run source and engine manifests match; saved index metadata matches the frozen preflight. No pre/post SQLite-byte hash was collected, so the report does not claim that stronger gate. The read-only invocations and recorded commands contain no index mutation. Raw event/stdio captures, source and runtime are retained locally at `.omx/observations/caller-heldout`; tracked results exclude raw reasoning.

This held-out target is within the same caller family and repository, not an independent repository benchmark or a causal old-JSON/new-text comparison. The earlier compact-caller and continuous-task regressions remain part of the record. Further same-family prompt tuning is not justified by this result; the next evaluation should test a different relationship task where multiple graph hops replace repeated navigation, with a separately reviewed quality oracle. Overall token savings remain unproven.
