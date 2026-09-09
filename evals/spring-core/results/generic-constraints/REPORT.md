# Spring correlated generic constraint comparison

Compared the previous resolver's saved index against a fresh candidate-parser index on Spring Framework `4c8c6409a27a62ab163d3b6196ad862b7c835440`, restricted to spring-core. All 1,166 source hashes match before/after and remain unchanged on disk. Removing only newly added argument/context/return-type fields leaves identical syntax facts. The baseline is the [type receiver audit](../type-receiver-review/REPORT.md).

Call edges change **9,349 → 9,174**: 32 additions and 207 removals. All 32 positive generic calls lost in the previous audit are restored. The 207 removals are insufficiently verified calls, not 207 compiler-proven false edges. Net stored-call coverage decreases by 175. [Exact edge identities and reasons](comparison.json).

| Unresolved reason | Count |
|---|---:|
| Bounds or explicit type arguments | 144 |
| Invariant argument unsupported | 21 |
| Value type unknown | 15 |
| Declaring-type substitution | 14 |
| Invariant constraint conflict or unknown | 8 |
| Parameter shape unsupported | 5 |

The complete archive is 5,009,364 bytes, up from 4,790,642 (+4.57%); the new SQLite cache is 108,814,336 bytes. It contains 20,811 nodes, 31,408 edges of all kinds and 68,007 references, with two diagnostics and `semantic_complete=false`. Its SHA-256 is `0514c96a21425e20c1828d2ed29f389dbb5dcc9b5cc57ba79f2881b62aaddd75`. [Archive receipt](archive.json).

A source-free `asArray` lookup in an empty directory returns one node in 796 bytes under a 2,048-byte budget and creates no SQLite file. [Consumer receipt](consumer.json), [response](archive-search.json). The local archive is retained under `.omx/observations/spring-generic-constraints/`; large SQLite and archive files are not committed.

Reproduction uses `evals/spring-core/compare_generic_constraints.py --repo <spring-core> --baseline <prior-index-and-removed.jsonl-directory> --output <new-directory>` with the candidate runtime on PYTHONPATH. The baseline SQLite is retained locally at `/tmp/columbus-spring-type-receiver-review/index.sqlite`; this comparison requires that prior artifact. The compiler gate uses reduced generated cases; Spring itself was not compiled or executed. Storage/query observations are not actual model-token savings.
