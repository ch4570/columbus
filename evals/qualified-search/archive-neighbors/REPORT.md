# Stored relationships directly from a portable graph

`archive-neighbors EXACT_ID --input GRAPH.jsonl.gz` now returns one-hop stored edges and endpoint declarations without rebuilding SQLite. It supports in/out/both directions, edge-kind filtering, an edge-count cap and a complete JSON byte budget. Exact IDs avoid silently selecting one ambiguous declaration; discover them with archive-search.

The implementation makes two streaming passes, retaining at most 50 selected edges and their endpoints rather than loading the complete graph. Both passes validate final archive record counts even when output is capped. A single open file descriptor and before/after file metadata detect changes during reading. Truncated output removes orphaned endpoint nodes. Responses expose source hashes, unchecked source freshness, stored-edge/runtime uncertainty, global unresolved/diagnostic counts, total matching edges and semantic_complete=false. This does not add multihop inference or unresolved candidate edges.

Tests compare in/out/both results to original SQLite edge rows after deleting source and SQLite, including a self-loop counted once, count/byte caps, exact-ID rejection, incomplete archives and modification between passes. Both engine suites pass 212 tests; the final four-test archive suite includes the added mutation check; root tests pass 53. Skill validation and clean wheel installation pass. The distribution probe now invokes source-free relationships as well as archive search.

On the unchanged existing Spring artifact (5,009,364 bytes), a source-free CLI query returns all six stored getResource call edges and endpoint metadata in 6,368 bytes under a 16,000-byte cap. Exact edges match the saved SQLite snapshot, the archive SHA-256 is unchanged, and no consumer files/SQLite are created. One observed CLI call takes 1.048 seconds with unflushed OS caches. [Raw receipt](spring.json). This is storage-backed navigation evidence, not a latency benchmark or actual model-token savings result.

Hosted validation for this feature is pending. The preceding qualified SQLite lookup's candidate matrix completed successfully; it does not cover this new archive command.
