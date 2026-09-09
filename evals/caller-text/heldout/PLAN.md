# Predeclared held-out caller target

Run one baseline trial followed by one Columbus current-skill trial, both requested gpt-5.6-sol/xhigh, 600-second timeout. Freeze current engine, skill and immutable c67b20a source before either model run. Use the existing exploration harness and its exact-citation, expected call-line and complete caller-ID gates. Review explanations separately. No selective retries or post-result prompt changes.

Target read_stable has not been used in earlier model comparisons. An independent Python AST walk identifies RepositoryIndex.refresh (139,170), RepositoryIndex.status (317,327), and RepositoryIndex._source (441). Source review confirms the explicit .sync_state import, no alias, no read_stable store or parameter rebinding in index.py, and no other direct Name calls elsewhere in the frozen package. Expected IDs/counts remain hidden from the model prompt.

This changes the target within the same task family and repository; it is not a broad held-out repository benchmark or a causal comparison against the old JSON skill. Include the full skill/routing overhead and any redundant reads in actual runtime counters. Compare only if both quality gates and the source/engine/index integrity checks pass. Preserve a regression or failure in full. No token-savings goal completion can follow from this one pair.

Preflight note: an initial mistaken .discovery import assumption failed the independent AST check before any model run. It was corrected to the actual .sync_state definition/import, and preparation uses a fresh output directory.
