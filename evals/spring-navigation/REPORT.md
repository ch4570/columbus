# Spring resource navigation: quality gate failed in both conditions

The predeclared pair completed without retries or timeouts. Both answers correctly describe the eight reviewed mechanisms, but both fail verbatim citation requirements. The baseline stitches the FileUrlResource declaration/field to a constructor across omitted source. Columbus repeats that error and omits an intervening comment from the UrlResource quote. These are recorded failures; the gate was not relaxed after seeing results.

| Measurement | Baseline | Columbus condition |
|---|---:|---:|
| Input tokens | 157,751 | 121,235 |
| Cached input (subset) | 122,752 | 77,056 |
| Uncached input | 34,999 | 44,179 |
| Output tokens | 7,783 | 8,880 |
| Reasoning output (subset) | 5,001 | 6,230 |
| Shell commands | 12 | 24 |
| Command output bytes | 75,335 | 54,799 |
| Seconds | 276.499 | 299.691 |
| Grounded citation findings | 7/8 | 6/8 |
| Accepted overall quality | Fail | Fail |

Total input decreases 23.15%, while uncached input increases 26.23% and output increases 14.09%. These descriptive counters do **not** establish savings at accepted quality. Furthermore, the Columbus condition reads the skill but uses no graph commands; it performs ordinary rg and numbered source reads, including repeated ranges. This does not test graph retrieval effectiveness. More shell commands with smaller combined output also do not by themselves establish lower model cost.

The 1,166-file / 7,120,331-byte Spring snapshot, engine/skill and cases were frozen before both runs; the executable plan was committed as 9134be5. Baseline ran first, both requested gpt-5.6-sol/xhigh, 600 seconds each. The same prebuilt index was available only to the Columbus condition. Source/runtime manifests, index revision and database byte hash remain unchanged after both trials. No target build/runtime was executed. This is one new task on an already source-reviewed repository, not a held-out or population-level result.

[Actual results, answers and command traces](results.json), [manual semantic review](semantic-review.json), [before](pre-run.json) and [after](post-run.json) validation. Full events, prompts and invocation settings are preserved in `.omx/observations/spring-navigation/` and `/tmp/columbus-spring-navigation-frozen/trials/`. The harness uses Codex's [non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode); runtime counters, rather than byte estimates, supply this table.

The experiment exposes two adoption/quality gaps: the available skill did not cause graph use on this flow-navigation task, and both agents rewrote supposedly verbatim evidence. Do not retune and repeat this pair until it passes. Future changes need evidence that a workflow actually uses graph-delivered source and preserves citations, followed by a different predeclared task. Overall token savings remain unproven despite completed storage and platform improvements.
