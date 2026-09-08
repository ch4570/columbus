# Requests redirect-flow second observation

The second Requests pair fails the unchanged quality-preserving savings gate. Baseline and Columbus each completed once, with one completed model turn, verified event hashes and unchanged source/runtime/input manifests and archive postflight. No retry or timeout occurred. This is a known-task repeat with the same question and eleven criteria, not a held-out task or independent repository sample.

| Measure | Baseline | Columbus |
| --- | ---: | ---: |
| Total input tokens | 423,075 | 560,053 |
| Cached input subset | 354,560 | 514,432 |
| Uncached input | 68,515 | 45,621 |
| Output tokens | 13,998 | 15,733 |
| Reasoning output subset | 9,614 | 10,024 |
| Seconds | 488.875 | 545.198 |
| Completed commands | 17 | 38 |
| Command output bytes | 94,278 | 88,441 |
| Failed commands | 0 | 4 |
| Bounded citation checks | 7/11 | 10/11 |
| Semantic checks | 9/11 | 8/11 |

Total input rose 32.377% and output 12.395%, while uncached input fell 33.415%. Cached and reasoning counts are subsets. Less source output and lower uncached input do not satisfy the declared total-input/output gate, and neither answer passes all quality criteria. Differences from the first pair cannot be attributed solely to runtime changes: even the unchanged baseline varies substantially between observations.

Both explanations omit response-hook ordering, default following, history/final-response rearrangement and non-stream content consumption in dispatch. Both correctly explain status-based body removal but omit the required rebuild_method-before-purge ordering. Columbus additionally omits post-send session cookie extraction; baseline states it. The remaining eight semantic findings pass for both. Actual quotes can substantiate missing prose, but citing a broad range alone cannot. Per-finding reviews retain the decisions and separate citation failures. Baseline omits source comments in three quotes and misses the frozen initial-fragment marker; Columbus omits a source comment in method_policy. No scoring rules were relaxed after launch.

The new archive-source path was used successfully: 16 verified declaration pages returned 27,655 physical-source bytes, including 1,212 repeated bytes. Across all recognized src/ reads, baseline returned 63,173 bytes (6,471 repeated) in 34 ranges; Columbus returned 47,356 bytes (4,034 repeated) in 29 ranges. All recognized ranges verified; this diagnostic excludes rg, unsupported commands, metadata and skill text. It is not token usage, attention measurement or a claim that every repeat is avoidable.

Qualified caller lookup succeeded for requests.sessions.Session.send. The source API still required exact IDs: two import-like queries failed, followed by a guessed Session.resolve_redirects ID that also failed because the declaration belongs to SessionRedirectMixin. A fourth failed command searched a nonexistent requests directory rather than src/requests. Later exact-ID body reads worked without resolved graph edges. This supports further investigating a consistent declaration-selection interface; it does not establish that eliminating those failures would reverse the measured token regression.

The graph remains 173,816 bytes, 112 files, 883 nodes and 1,188 edges. Previous failures remain recorded. No comparison in the ten-pair recent overview establishes accepted quality-preserving total-token savings, and the full issue-driven project goal remains incomplete.
