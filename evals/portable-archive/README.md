# Complete portable graph archive validation

2026-09-08 KST. `archive` now writes all indexed graph facts as deterministic gzip JSONL; `archive-search` returns bounded declaration evidence directly from that artifact without source files or SQLite. This completes a lightweight, repository-storable graph path, while the existing SQLite cache remains the full-text/traversal workspace.

Spring snapshot: 1,166 indexed files / 7,120,331 source bytes. The artifact is **4,647,698 bytes** and includes 20,811 nodes, 30,712 edges, 20,647 scopes, 68,007 references, 7,723 import records and 16 diagnostics. No node/edge view limit applies. Every node and edge record matched the complete SQL result, not a bounded graph export. [Raw verification](results/spring.json) retains counts, archive hash and a 1,667-byte query response under a 2,048-byte budget.

The archive includes signatures, docs, source spans/hashes, parse status, binding scopes, relationship evidence and unresolved facts. It excludes source bodies, FTS copies and local root/stat/worktree metadata. It is not a restorable SQLite backup or a compiler-complete graph. In particular, current conservative JVM guards reduce emitted call coverage, and the shipped pinned Java grammar still reports known partial files. The artifact preserves these limitations.

A real [example artifact](../../examples/polyglot-demo/graph.jsonl.gz) is checked in: 3,466 bytes, 28 nodes, 25 edges, 11 files. The source-hash snapshot may differ from future revisions; compare hashes before editing. The skill describes archive creation and bounded lookup in its [archive reference](../../skills/columbus/references/archive.md).

Validation:

- 188 engine tests passed; final focused archive regressions passed after adding import preservation. The fixture exceeds 5,000 nodes, verifies full node equality and counts, checks deterministic bytes and collision refusal, preserves import/reference records, and rejects missing end records. Simulated cache corruption leaves no partial published artifact or temporary file.
- 49 root tests, compilation and skill quick_validate passed locally.
- A built wheel queried the relocated example under isolated Python, with no source repository or SQLite cache. [Consumer receipt](results/wheel.json). Dependencies came from the existing development interpreter; this is an isolated import/consumer check, not a clean platform matrix.
- Complete Spring graph equality and a bounded exact-name lookup passed. Archive search is a streaming scan, not a latency-optimized index; no model-token or compiler-precision gain is claimed.

Reproduce:

```sh
columbus archive --repo /path/to/repo --output /new/path/graph.jsonl.gz
columbus archive-search DefaultResourceLoader --input /new/path/graph.jsonl.gz --budget-bytes 2048
.venv/bin/python evals/portable-archive/verify.py /new/path/graph.jsonl.gz /path/to/repo/.columbus/index-v1.sqlite
```

The verification script's named-query assertion targets the recorded Spring corpus. `--snapshot` archives existing evidence without syncing. Existing output files are never replaced; publish is atomic via a same-directory hard link. Filesystems without hard-link support fail rather than publish partial output. Hosted Windows/Linux and final wheel/ZIP integration remain to be verified.
