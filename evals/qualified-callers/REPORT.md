# Exact Python module-qualified caller targets

The HTML model trial's first callers query used django.utils.html.conditional_escape and failed, requiring search and an exact-ID retry. The caller API now falls back to an exact recorded Python module.qualname match after existing ID/name lookup. It uses the final name component to narrow indexed candidates and compares complete stored identity; it does not infer a target from a filesystem suffix or use the caller path filter to choose among ambiguous targets.

On the retained frozen Django index, the qualified-name query and exact-ID query produced identical complete packets for all 12 production callers with path django/*, context 20 and a 20,000-byte budget. This was a read-only tool check, not a model replay. The failed experiment remains unchanged; no token savings are claimed.

Regressions cover package __init__ identity, another module with the same short name, false prefix rejection, ambiguity independent of caller path filters, and colliding package/module import names. Both engine environments pass 221 tests; root tests pass 53 and the updated skill validates. Existing ID/name lookup takes priority, and ambiguous qualified names still require an exact symbol ID.
