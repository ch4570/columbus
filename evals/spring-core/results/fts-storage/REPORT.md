# Compressed FTS storage in the index

Schema 4 stores search document bodies as compressed UTF-8 and indexes them through an external-content FTS view. Read connections register the decoder. Document deletion, replacement and index rebuilding share the snapshot transaction. Schema 2/3 remain readable and upgrade on sync; failed upgrades preserve the preceding schema and search results. Older engines require a separate DB after upgrade.

Same-source Spring comparison against index implementation fc0b65f, using the same current candidate parser/resolver:

| Measurement | Before | After |
|---|---:|---:|
| Fresh DB bytes | 108,814,336 | 96,677,888 |
| Unchanged API sync median, 5 runs | 0.4194 s | 0.4333 s |
| One-file edit, one run | 3.0685 s | 3.0939 s |
| Cold build, one run | 5.6271 s | 5.9861 s |

Fresh storage decreases 11.15%. Timings show no speed improvement. OS caches were not flushed; baseline ran first on an uncontrolled shared host. The production path includes an index for document-path deletion and has not been vacuumed, so its size is not the earlier vacuumed prototype result. [Raw comparison](comparison.json).

All symbol/edge rows match before and after the source edit; restoring source restores both graphs. All twelve API search hit lists and rankings match. A separate actual schema-3 Spring DB upgrades to schema 4 with equal graph rows and search, valid FTS integrity, and a warm sync that parses/loads zero cached facts. Its file remains 108,814,336 bytes because SQLite retains free pages: migration does not automatically shrink old files. [Migration receipt](migration.json).

Both parser engine suites pass 209 tests; root tests pass 53. The final 20-test sync suite includes real schema-3 FTS layout migration, injected migration failure, replacement/deletion and a failure after FTS writes that rolls back to previous search results. Existing stale-source checks pass. Clean wheel installation validates schema 4 and normal distribution navigation. Skill validation passes. Hosted platform validation is pending.

The portable complete graph archive remains a separate repository artifact. This storage change does not establish semantic completeness or actual model-token savings. One-file changes still globally relink.

A follow-up concurrency check keeps a real schema-3 reader transaction open while another connection completes migration. That reader retains schema 3 and identical FTS document rows; a new reader observes schema 4 and unchanged search results. The 20-test sync suite passes in both parser environments with this assertion. This covers overlapping read/write connections in one process, not arbitrary concurrent writers or every platform.
