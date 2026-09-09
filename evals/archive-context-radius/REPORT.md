# Source radius for behavior explanations

The saved-archive skill example used a two-line radius, while its live-index behavior guidance suggested twenty. The saved-archive route now makes the same task-dependent distinction: a small call-site excerpt for locating calls, and an initial twenty-line radius for explaining behavior, adjusted to include relevant branches before and after the call. This is guidance, not a CLI default change.

On the unchanged urlencode trial artifact (SHA-256 in results.json), scoped incoming queries with a 20,000-byte text budget returned the identical seven call sites in one page at every measured radius:

| Radius | Output bytes | RequestFactory.generic excerpt |
| --- | ---: | --- |
| 2 | 8,000 | lines 663–667 |
| 4 | 8,738 | lines 661–669 |
| 20 | 13,974 | lines 645–671 |

The four-line excerpt ends at `if not r.get("QUERY_STRING"):`. The twenty-line excerpt also contains the fallback assignment and return. It therefore provides more relevant behavior in the initial query, at greater output cost. The original model later read source containing that fallback and still misstated its behavior; lack of initial context is not established as the sole cause of the failed answer. Wider context does not prove correct reasoning, fewer commands or lower model usage.

Measurements use the current neighbors_archive implementation, exact target `django/utils/http.py::urlencode:function`, direction `in`, kind `calls`, path `django/*`, text format and the original trial's source repository. results.json retains page offsets, source hashes, ranges and all call identities for each radius. The archive hash is unchanged. No model trial was replayed, no frozen input was changed, and the skill validator passes.
