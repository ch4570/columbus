# Reuse declaration scan for archive caller edges

archive-callers previously decoded the complete archive three times: resolve the identifier, select incoming edges, then collect bounded endpoint metadata. A Django profile recorded 1176483 JSON decodes across those passes. Its 7.426-second profiled duration includes instrumentation overhead and is not a benchmark comparison.

The first scan now also counts references/diagnostics and selects bounded incoming edges when declarations precede edges, as the exporter writes them. A second complete validated scan obtains endpoint nodes and file hashes. Any node after an edge triggers the original separate edge scan, preserving support for arbitrary valid record orders. The method keeps at most the requested edge limit, preserves exact-ID precedence and ambiguity rejection, and checks complete record counts and archive changes. Public archive-neighbors behavior is unchanged.

Three fixed-order samples per condition on the same immutable full Django archive produced these source-free caller-query medians:

| Codec | Before seconds | After seconds |
| --- | ---: | ---: |
| Gzip | 3.188945 | 2.135173 |
| XZ | 4.556346 | 3.041555 |

Both decrease by about one third. All twelve returned packets have the same full canonical hash, 46 call sites and next_offset=null. Runtimes differ only in archive.py; the baseline file is frozen from 1ad68b9. Gzip is a temporary recompression of the identical XZ JSONL. Timing order is gzip before XZ and baseline before changed runtime, with three calls in each worker, unflushed OS caches and other local tests stopped during measurement. This is a bounded diagnostic comparison, not a causal population estimate or model token result.

The documented 12000-byte/radius-20 context traversal also produces exactly the earlier six-page verifier result, including source hashes/excerpts, 37 owners and same-line multiplicity. Source-free gzip/XZ fixtures verify two passes for exporter order, three for reordered records, exact pagination, and rejection of a missing end record despite an edge limit of one. Existing ambiguity, stale-source, scope and byte-budget checks pass.

Ordinary and candidate parser engine suites each passed 236 tests; root suite passed 53. Fresh wheel/ZIP distribution validation passed. Results and runtime hashes are retained here. No new model trial was run, previous frozen inputs remain unchanged, and the semantic-quality/remaining issue requirements are not declared complete.

## Snapshot and late-declaration controls

Additional gzip/XZ checks replace the archive after the resolution/edge scan and before the endpoint scan. The replacement has identical contents, size and modification time, so it specifically tests rejecting a changed file identity rather than merely finding a length difference or corrupt data. The query rejects the replacement; a fresh query against the stable replacement succeeds. This is conservative snapshot identity validation, not a claim that identical replacement bytes contain different graph facts.

A valid archive reordered to put nodes after edges also gains a late same-name declaration. Name-based callers reject the ambiguity after consuming the archive; an exact-ID query still equals incoming neighbors. These controls complement the existing fallback/pass-count and incomplete-tail checks.

Both engine environments passed 237 tests. No production code changed in this follow-up, so the previously measured timings and source-context equality were not remeasured. Hosted run 34178929158 for the implementation commit was still in progress when checked; local tests do not stand in for its pending platform conclusions.

Remote implementation run 34178929158 at 2fb7b8d and follow-up snapshot-test run 34179127554 at 5825237 both completed successfully in all six platform jobs. platform-final.json and snapshot-platform-final.json retain the exact conclusions.
