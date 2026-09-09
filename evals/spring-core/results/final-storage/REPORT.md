# Final index-layer comparison with current JVM guards

2026-09-08 KST. Both index implementations use the same current language parser/resolver; only the index implementation is swapped against commit 4d55a34. Thus graph parity measures the storage change, not parity against historical JVM call semantics. Corpus, source hashes, current index hash and all raw runs are in [summary.json](summary.json).

| Measurement | Previous index layer | Current index layer |
| --- | ---: | ---: |
| Fresh database bytes | 199,913,472 | 106,995,712 |
| Unchanged API sync median, five runs | 1.0346 s | 0.5016 s |
| One-file edit, one observation | 2.9748 s | 2.9921 s |
| Cold index, one observation | 4.7378 s | 4.8700 s |

Storage decreased 46.5%; unchanged sync decreased 51.5%. The one-file edit and cold observations do not demonstrate an improvement; global relinking remains. OS caches were not flushed, baseline ran first and host load was uncontrolled. API times exclude process startup.

Every stored node/edge row matched before and after the one-file edit; all twelve listed search responses/ranks matched; restoring the file restored both snapshots. Single edit/cold measurements are not robust timing estimates. Current graph coverage is conservative and differs from older resolver releases. This validates index-layer preservation, not compiler correctness or model-token savings.
