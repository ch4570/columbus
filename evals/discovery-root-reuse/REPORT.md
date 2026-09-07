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
