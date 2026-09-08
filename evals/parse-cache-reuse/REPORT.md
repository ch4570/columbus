# Reuse unchanged resolved parse cache blobs

On a complete isolated Django copy, a comment edit leaves 5465 of 5466 compressed resolved parse blobs byte-identical. Renaming iri_to_uri changes ten cache blobs, including nine files whose source did not change. probe.json retains those paths and proves why source-file identity alone is not a sufficient cache reuse condition. Restoring either edit restores every original blob.

Refresh still loads all cached facts and globally relinks them. During decoding it retains a SHA256 of the existing serialized facts. After relinking it serializes the final facts and reuses the existing parsed column only if that digest matches; changed facts are compressed and replaced. Removed file rows are deleted individually. File hash/size/stat metadata and the graph/search tables continue to update in the same transaction. This avoids retaining another full copy of decompressed facts in memory and changes neither schema nor invalidation policy. It does not eliminate global relinking or serialization.

The new regression test stores a valid alternate-compression blob for an unrelated file, then renames an imported target. The unrelated blob survives byte-for-byte, the unchanged-source caller's blob changes to unresolved, and all decoded caches plus the public graph match a fresh rebuild. Existing deletion, source-change, rollback and schema upgrade tests also pass.

Full Django before/after runtimes differ only in index.py (baseline 279416c). Initial, comment-edited and renamed snapshots have identical full parsed facts, symbol/edge tables, logical FTS documents and six complete ordered search results. Restorations equal the initial snapshot. Logical search document comparison excludes physical rowid only. comparison.json retains hashes/counts of the complete comparisons; full temporary snapshots remain under /tmp/columbus-cache-reuse-django.

| Measurement | Before | After |
| --- | ---: | ---: |
| Comment edit seconds | 7.132411 | 6.597507 |
| Function rename seconds | 12.600298 | 6.252926 |
| Five unchanged syncs, median seconds | 1.973122 | 2.084266 |
| SQLite bytes after sequence | 153391104 | 153391104 |

The comment observation improves about 7.5%. The rename observation has an unusually large difference; this single sample does not justify a general 50% speedup claim. Unchanged sync is about 5.6% slower in these samples and database size is unchanged. Both workers run sequentially before/after with unflushed OS caches and no concurrent local tests/builds. These diagnostic timings do not isolate cache/host effects. The cache-byte and full-result invariants are stronger evidence than the timings.

Ordinary and candidate engine suites each passed 239 tests; root suite passed 53. No model trial ran, and no new model token savings or semantic correctness claim is made. Remaining costs include global relinking, JSON serialization, graph-table reconstruction and source discovery.

Fresh wheel and ZIP distribution verification passed; see distribution.txt.
