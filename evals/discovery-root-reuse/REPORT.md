# Reuse the canonical discovery root

Discovery now resolves the repository root once per invocation and reuses that canonical containment boundary. Every candidate still receives its own symlink, resolution and containment checks. File classification, text probes and stable reads are unchanged. The new regression checks valid paths, parent traversal and replacement of the canonical root with an outside directory symlink.

On the same Django checkout (4ea267661b260ea0d0c87e9dcb99d70037c6f2fc), separate temporary copies and fresh indexes were measured with `evals/django-sync/measure.py`, first at f9ce33c and then with this discovery change. Each measurement includes three unchanged fast refreshes; the separately profiled refresh is excluded from the median. Other local tests were stopped during measurement. OS caches were not flushed and execution order was fixed, so these are diagnostic observations, not a controlled causal benchmark.

| Observation | Before | After |
| --- | ---: | ---: |
| Unchanged refresh median, seconds | 2.4413 | 2.2069 |
| One-file edit, seconds | 8.7382 | 8.5428 |
| Database bytes | 153,387,008 | 153,387,008 |
| Discovery probe bytes per refresh | 48,973,750 | 48,973,750 |
| Profiled Path.resolve calls | 49,309 | 35,593 |

The observed median fell 9.6%. Probe I/O and storage did not decrease. The before/after discovery outputs compare exactly: all 5,466 paths and the entire inventory dictionary match. parity.json records discovery code hashes. Both measurements retain 46,631 symbols and 86,828 edges through an edit and restoration, and their limited iri_to_uri search IDs remain stable. Counts and this limited search are not a complete graph or ranking parity proof.

Ordinary and candidate parser engine suites each pass 230 tests; root tests pass 53. These include stable-read and stale-source regressions. A newly built wheel and portable ZIP also pass clean installation, relocation, stale-source, archive and caller verification (distribution.json). Test logs and raw measurements are retained here. This Django diagnosis does not fulfill the separate Spring corpus acceptance criteria in issue #6, establish cross-platform performance, or demonstrate actual model token savings. No model experiment was run.

## Spring follow-up

`measure_spring.py` freezes the before runtime at f9ce33c and after runtime at 596e713, verifies that only discovery.py differs, and creates independent source copies and fresh databases. Spring revision 4c8c6409a27a62ab163d3b6196ad862b7c835440 yields the same 1,166 indexed files using the candidate Java grammar. No local test suite ran concurrently with these measurements. The order remains before then after, OS caches remain unflushed, and five warm samples are collected per runtime.

| Spring observation | Before | After |
| --- | ---: | ---: |
| Unchanged refresh median, seconds | 0.40939 | 0.37734 |
| One-file edit, seconds | 3.04218 | 2.99919 |
| Database bytes after edit/restoration | 96,677,888 | 96,677,888 |

The observed warm median falls 7.8%; the caveats above prevent attributing a universal speedup to this sample. Editing Assert.java parses one file and globally relinks in both versions. This change does not reduce that relink work or database storage.

spring-comparison.json records runtime hashes, every source hash, complete parsed-fact hashes, and hashes over every column of all 20,811 symbols and 31,408 edges. All match exactly between versions. All 20,811 logical search documents (ID, name, path and compressed body) also match, and complete ordered hits including retrieval scores match for six declared queries. Restoring the edited source reproduces each version's initial snapshot exactly under those comparisons. The callers suite was rerun separately after measurement, including its explicit stale-source rejection test (spring-stale-tests.txt). These supply the same-corpus regression and latency evidence requested by issue #6 for this bounded optimization; they do not establish completeness of every JVM target or actual model token savings.

The first verifier failed because it also included SQLite search_documents.rowid in edit/restoration parity. File reinsertion can change that physical FTS address. spring-harness-failure.json preserves the mismatch and the unchanged facts, symbol/edge hashes and selected search results. The corrected verifier excludes only that internal address and retains every logical document field. This was a verifier correction, not a runtime change or discarded model result.

The exact discovery runtime at 596e713 also passed all six distribution CI jobs in run 34171167820 (Linux, macOS and Windows, Python 3.11 and 3.14); platform.json records the revision and conclusions. These are functional platform checks, not platform timing measurements.
