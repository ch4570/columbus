# Revised caller workflow: early graph use, mixed efficiency

Both fresh trials passed the exact seven-caller set, contiguous citation checks and source-based explanation review. The revised skill successfully moved graph search and incoming-call traversal to commands **2 and 3**, immediately after skill loading. Both graph commands succeeded with the complete ID. Source/settings remained unchanged; no timeout or selective retry occurred. Columbus ran first, as predeclared.

| Measure | Baseline | Columbus |
| --- | ---: | ---: |
| Input tokens | 67,809 | 148,435 |
| Cached input subset | 30,464 | 134,656 |
| Uncached input | 37,345 | 13,779 |
| Output tokens | 2,666 | 4,136 |
| Command output bytes | 64,323 | 30,462 |
| Commands | 12 | 15 |
| Elapsed seconds | 97.044 | 154.951 |

Command output decreased **52.64%** and uncached input **63.10%**, but total input increased **118.90%**, output **55.14%**, and time **59.67%**. Do not select only the favorable metric or infer billing savings. This single pair does not establish general savings or isolate a causal effect from cache/order variation.

After graph narrowing, Columbus performed seven separate bounded source-read commands plus focused binding/coverage checks. The trace is consistent with repeated context accumulation across those interactions; this is an interpretation of the trace, not a provider-level token attribution. The sole nonzero command was ripgrep finding no matches, not a graph error. The new behavior fixes the late-graph and incomplete-ID pattern in the earlier pilot, but it does not yet meet the overall token-reduction goal.

[Complete evidence](controlled.json) includes both answers, grades, source/engine/skill hashes, prompts, commands, runtime usage, and graph command positions. Raw events and frozen runtime remain in `.omx/observations/caller-workflow-v2/`. The previous unfavorable pilot remains intact.

Next implementation: return caller identities and a bounded source-evidence range per caller in one graph query, retaining hashes, semantic uncertainty and truncation. Verify against the independent caller corpus and changed-source negative cases before a newly predeclared model comparison. Repeated-session and broader corpus validation remain outstanding.
