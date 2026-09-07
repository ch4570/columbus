# Bounded caller context after the failed model pair

Added an optional caller path glob, applied before grouping/counting/limiting, and 0–40 context lines around the first stored call, clipped to its lexical owner. Default excerpts retain their prior size. Context is hash-verified and the serialized byte budget still limits the response. The text header reports requested filters; counts describe matching callers. Multiple distant calls and comments outside the owner can still require separate evidence.

A deterministic query on the retained frozen Django index using path django/*, context 30 and a 24,000-byte budget returned all 12 production callers in 12,169 bytes. All 15 independently reviewed call lines lie in these excerpts. A 2,048-byte query stays within its budget and reports truncation. This does not establish complete behavior context, runtime completeness or token savings. The failed model pair is not replayed; its evidence remains unchanged.

Regression coverage checks filtering before the limit, matching counts, exclusion of a stale out-of-scope file, rejection of stale included source, lexical range clipping, zero context, multiple call-site counts, empty filters and invalid context values. Both parser environments pass 217 engine tests; the root suite passes 53 tests. The first new fixture used an ambiguous target module/function name; it was corrected to use the documented exact symbol ID.

The skill entrypoint now exposes path filtering and optional context expansion at the direct-caller decision, without forcing a wide window for simple enumeration. Reproduce the public CLI checks with:

```sh
.venv/bin/python evals/django-callers/context-options/verify.py /tmp/columbus-django-callers-frozen/repository /tmp/caller-cli-check.json
```

The verifier checks all 883 production source hashes, the exact caller set, all 15 call lines, exact excerpt/source equality, text budget and small-budget truncation. cli-verified.json records the observed public CLI response checksum. Skill validation also passes. This verifies documentation wiring and command behavior, not model routing or token savings after the change.
