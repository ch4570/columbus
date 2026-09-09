# Cache Python module namespace prefixes

A one-file-edit profile on an isolated Django copy found 15623821 iterations in the module-prefix fallback used by attribute resolution. The resolver repeatedly scanned all module names to decide whether a candidate was a namespace package. The profile also found cache encoding/compression costs, but those were smaller; no cache-write skipping was implemented.

The resolver now constructs a set of complete module names and prefixes ending at dots once, before resolving references. Membership is equivalent to the previous exact-name-or-dot-prefix predicate. Existing binding, import, ambiguity and receiver rules are unchanged; the set is runtime-only and adds no archived facts or database schema. A regression test distinguishes company.pkg.helper from partial component names such as company.pk and company.pkg.hel.

Full Django comparison freezes the baseline package at 5825237 and changes only parser.py for the after runtime. Each worker copies the same source, creates an index, runs five unchanged syncs, appends a comment to encoding.py, syncs, restores the source and syncs again. Every parsed fact, complete symbols/edges table, logical search document (including compressed body), and six ordered search result sets match before versus after in both initial and edited states. Each restored state equals its own initial state. Physical FTS rowid is excluded because reinsertion can change it without changing any searchable data. Source manifests, table/fact hashes and runtime manifests are retained in comparison.json; full temporary snapshots remain under /tmp/columbus-prefix-django.

| Measurement | Before | After |
| --- | ---: | ---: |
| One-file edit seconds | 8.259364 | 7.067725 |
| Five unchanged syncs, median seconds | 1.923394 | 1.931070 |
| SQLite bytes | 153391104 | 153391104 |

The single edit observation improves about 14.4%; unchanged latency and database size do not improve. Runtimes run sequentially before then after, OS caches are not flushed, and other local test/build work was stopped during measurement. These are bounded same-host observations, not a universal speedup. Profiling times include instrumentation overhead and are not directly compared with these timings.

Both engine parser environments passed 238 tests; root suite passed 53. The optimization retains global relinking and full cache rewriting. It addresses one measured cost from issue #6, not complete incremental linking, JVM coverage or the unresolved semantic-quality/model-token goal. No new model trial was run.

Fresh wheel and ZIP distribution verification also passed; see distribution.txt.

Remote run 34179671415 at 279416c completed successfully in all six platform jobs; platform-final.json retains the result.
