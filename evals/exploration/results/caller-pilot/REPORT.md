# Direct-caller pilot: correct answers, increased tokens

Both predeclared trials found exactly the seven independently reviewed direct callers and passed all source-citation checks. Explanation review confirmed import bindings, nested ownership and exclusion of indirect callers. Source/settings matched and both runs completed without timeout. Nonetheless, the Columbus condition used substantially more tokens.

| Measure | Baseline | Columbus |
| --- | ---: | ---: |
| Input tokens | 57,808 | 224,187 |
| Cached input subset | 37,248 | 197,248 |
| Uncached input | 20,560 | 26,939 |
| Output tokens | 2,889 | 4,651 |
| Shell commands | 13 | 16 |
| Command output bytes | 42,303 | 85,502 |
| Elapsed seconds | 102.057 | 172.622 |
| Graph attempts / successes | 0 / 0 | 4 / 3 |

Input increased **287.81%**, uncached input **31.03%**, and output **60.99%**. This is a quality-passing regression, not a savings result. One pair cannot establish average performance or billing cost.

The command trace explains a concrete improvement opportunity: Columbus performed ten shell/source reads before graph search, duplicating exploration instead of using the graph to locate callers first. It then passed an incomplete ID to neighbors, omitting `:function`, even though text search had returned the complete ID. A second search in JSON and corrected neighbors command followed. This was not text-output ID truncation. The graph ultimately returned the reviewed caller set, but arrived too late to reduce source exploration.

[Controlled evidence](controlled.json) retains answers, exact prompts/invocations, command/output hashes, full source/engine/skill manifests, measured usage and grades. Raw JSONL and snapshots remain in `.omx/observations/caller-pilot-24ae69b/`; model reasoning traces are not published. The frozen source and ground truth are unchanged from the caller corpus.

The next implementation step is a specific direct-caller workflow that narrows through incoming call edges before reading broad source ranges, preserves the exact target ID, and clearly reports semantic incompleteness. Test that workflow against this reviewed corpus before predeclaring another model comparison. Do not discard this failed-efficiency observation or redefine it as success because accuracy passed. Repeated-session savings and broader corpus accuracy remain outstanding.
