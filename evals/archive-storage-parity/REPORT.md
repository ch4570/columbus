# Full graph archive storage and fact parity

The existing exporter preserves all seven exported graph record categories on full Django and Spring snapshots. The verifier compares every file record, scope, import, reference, declaration, edge and diagnostic with the corresponding SQLite facts using ordered canonical hashes and counts. Gzip and XZ decompress to identical complete JSONL bytes. Database bytes and every indexed source hash are unchanged after export and validation.

| Corpus | Files | Indexed source bytes | SQLite bytes | Gzip bytes | XZ bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| Spring core, candidate Java grammar | 1166 | 7120331 | 96608256 | 5011708 | 3865576 |
| Django, ordinary parser environment | 5465 | 35218163 | 153391104 | 10726231 | 8592880 |

Spring XZ occupies 54.29% of indexed source bytes and 4.00% of SQLite bytes. Django XZ occupies 24.40% of source and 5.60% of SQLite. XZ is 22.87% and 19.89% smaller than gzip respectively. These are decimal byte comparisons to indexed source, not entire checkout/Git history sizes. Raw JSONL is 124610633 and 199045876 bytes respectively; compressed storage size does not imply cheap repeated decoding.

Spring preserves 20811 declarations, 31365 edges, 68007 references, 20647 scopes, 7723 imports and 2 diagnostics. Django preserves 46630 declarations, 86828 edges, 188003 references, 46964 scopes, 18268 imports and 1 diagnostic. Each JSON result retains all category hashes, source manifest identity, archive manifest/fingerprint and codec hashes. The Django XZ hash exactly matches the artifact used in the completed force_bytes-v2 model pair.

Reproduce with the repository virtualenv and appropriate parser PYTHONPATH: `verify.py DATABASE REPO OUTPUT`. Spring used the frozen 7bb9066 candidate index from the assignment comparison. Django was freshly indexed outside the frozen repository, using its unchanged source and current runtime; no consumer SQLite was created inside that source tree. Exporter/verifier hashes are in provenance.json.

Single gzip/XZ export observations were Spring 3.24/4.11 seconds and Django 6.42/7.54 seconds. Codec order was fixed, OS caches were not flushed, and the two corpora used different parser environments; these are diagnostic timings, not a controlled speedup claim. No source project builds or model calls ran for this check.

The archive excludes SQLite full-text documents and source bodies. Equality therefore covers the declared exported graph contract, not all SQLite functionality or every raw parse-cache field. Unresolved and partial evidence remains present; this does not prove compiler accuracy. The index amplification/warm-sync/edit-latency requirements of issue #6 remain separate, and semantic-quality failures still prevent accepting the observed model token reduction. The new evidence establishes full-corpus fact preservation and current portable storage cost, not completion of the whole project objective.
