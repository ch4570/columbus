# Reviewed Python caller corpus

On the frozen Columbus runtime at c67b20a, the module-level `index.compact` function has **7 direct lexical callers at 23 source locations**. Independent standard-library AST enumeration and source review agree with all Columbus call edges into that target: **23/23 sites, zero false sites or omissions**. This is a scoped result, not repository-wide or JVM precision.

Reviewed callers are `archive.emit`, `_search_archive`, CLI `main`, `RepositoryIndex.neighbors`, `RepositoryIndex.refresh`, `byte_size`, and `encode_parse`. Review inspected every `compact` occurrence: the archive and CLI modules explicitly import it from `.index`; the index module defines it; no calling scope rebinds it. The MCP function's unrelated `compact` parameter is not a call. Nested `emit` is the direct caller, not its enclosing `archive` function. Calls in comprehensions retain their enclosing function identity for this corpus.

[verify.py](verify.py) constructs expected call locations without invoking Columbus parsing/resolution. It requires every source hash to match the previously frozen fixture, checks the reviewed caller sets and explicit imports, and then compares SQLite edges. [compact.json](compact.json) retains complete locations, source hashes, graph revision and analyzer fingerprint. [Negative controls](negative-controls.json) show that deleting an edge and fabricating a call location in separate temporary database copies both fail the oracle. The original snapshot is preserved.

Reproduce after preparing the c67b20a fixture and freezing its current engine/index with the exploration harness:

```sh
.venv/bin/python evals/caller-corpus/verify.py /path/to/observation/repository /path/to/observation/repository/.columbus/index-v1.sqlite /tmp/compact-callers.json
```

This fixture can support an actual caller-enumeration task without deriving ground truth from the graph being evaluated. A future model comparison must require the exact caller set, distinguish direct callers from transitive impact, check source citations, include graph invocations and actual usage, and reject omissions and extra callers. No model measurement or repeated-context saving is claimed by this corpus preparation.
