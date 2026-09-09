# Compressed search-document storage feasibility

The current Spring index allocates 28,311,552 bytes to FTS's stored document copy. An isolated SQLite copy replaces that copy with a compressed body table and an external-content FTS view. Production schema and runtime are unchanged. Corpus: Spring `4c8c6409a27a62ab163d3b6196ad862b7c835440`; source index uses `fc0b65f` semantics.

| Database | Bytes |
|---|---:|
| Original | 108,814,336 |
| VACUUM-only control | 106,471,424 |
| Compressed external content, vacuumed | 92,446,720 |

The controlled difference is 14,024,704 bytes (13.17%); comparing only the original would incorrectly attribute compaction gains to compression. The standalone graph archive is separate and unaffected.

All 20,811 FTS document rows reconstruct exactly. Twelve existing Spring search queries return identical first 150 candidate IDs and BM25 scores, including ordering. An explicit FTS deletion removes the selected hit, transaction rollback restores it, and FTS integrity checking passes. Raw [receipt](summary.json). This is not full API/refresh or concurrency coverage.

The prototype requires registering the inflate function on connections that access the view. Production adoption still requires transactional schema migration, readable prior snapshots, incremental document replacement/deletion, stale-source and rollback tests, identical full API search/graph results, unchanged-sync and one-file-edit measurements, and supported-platform SQLite verification. No latency or actual model-token savings claim follows from this experiment.

Reproduce with `PYTHONPATH=skills/columbus/scripts .venv/bin/python evals/spring-core/probe_fts_storage.py --baseline <saved-index.sqlite> --output <new-directory>`. The local DB copies are retained at `/tmp/columbus-fts-compression-controlled`; large binaries are not committed.
