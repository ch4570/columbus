# Safe redirect saved-archive comparison

Both answers pass the exact caller/citation gate and manual review of the predeclared redirect behavior, but graph-assisted exploration uses more tokens in every main usage measure. This is another failed savings result, preserved without replay.

| Measurement | Baseline | Graph |
| --- | ---: | ---: |
| Elapsed seconds | 157.540 | 228.520 |
| Total input tokens | 29,960 | 90,104 |
| Cached input tokens | 18,048 | 71,680 |
| Uncached input tokens | 11,912 | 18,424 |
| Output tokens | 4,581 | 5,909 |
| Reasoning output tokens, subset | 3,244 | 3,990 |
| Commands | 3 | 8 |
| Command output bytes | 8,627 | 29,729 |
| Exact owners and citations | pass | pass |
| Reviewed redirect behavior | pass | pass |

Total input increases 200.75%, uncached input 54.67%, and output 28.99%. Baseline used one narrow rg query and two numbered source reads. Graph read the skill and archive reference, searched the archive successfully in text format, queried scoped incoming calls, then performed the same rg search and similar source reads plus the target utility body. It selected context-lines 2 and a 6,000-byte budget, despite the skill's newly added behavior guidance suggesting 20. The earlier unsupported text-format error did not recur, but the guidance change did not produce the intended wider initial context. The observed workflow adds graph setup to ordinary exploration; smaller graph packets alone do not address that duplication.

The task was selected before its inventory was inspected, then source/skill/runtime and predeclared semantic criteria were committed at a164c9b before either trial. Baseline ran first, graph second, once each, requesting gpt-5.6-sol/xhigh with 600 seconds per condition. Both completed normally. No model replay, prompt adjustment or timeout extension occurred. Backend identity is not independently attested. Two owners containing three direct calls make this a small task on the same Django repository, not an independent repository sample or a general result for relationship exploration.

Both answers distinguish the public imported utility and lexical owners, POST missing-key defaults, allowed-host values, secure-request options, validation short-circuiting, referrer revalidation, slash fallback and 204 behavior. Both cover the later valid-POST language redirect replacement. The graph answer does not describe cookie assignment; that omission does not contradict the requested redirect behavior and exact cookie details were not required. semantic-review.json records that boundary rather than silently treating all source details as mandatory. Both set_language call sites fall within the cited source ranges; the generic automated gate alone only requires one direct site per owner.

The independent oracle covers all 883 Python files under django/. Graph checks match all three scoped sites, while the complete incoming graph contains thirteen calls including excluded top-level tests. Pre/postflight source and runtime manifests, harness/schema/case/review hashes and archive checks all pass. The archive remains b93921c806a24628528d88c4045969f9d70b6236c415a62be23dcf6c903f39e6; no consumer SQLite is present. It contains 5,465 files, 46,630 nodes and 86,828 edges in 8,592,880 bytes. Producer indexing took 16.971 seconds and export 7.394 seconds, separately from model usage.

results.json retains answers, actual usage, commands and event hashes. Raw events remain in .omx/observations/archive-safe-redirect and the original /tmp/columbus-archive-safe-redirect-trial directories. The earlier failed pairs remain unchanged. Further work must address the observed additional exploration and demonstrate correct completed answers with lower actual usage; functional storage and retrieval checks do not complete that objective.
