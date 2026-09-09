# Filter saved relationships before pagination

Add `archive-neighbors --path GLOB`. The case-sensitive fnmatch filter applies to edge paths before matched-edge counts, offsets, limit selection and source-context reads. For incoming calls it restricts caller files without filtering out the target declaration. Keep the same pattern across pages. Repository-wide diagnostic and unresolved counts remain explicitly global. Default queries are unchanged.

The next prepared urlencode task exposed the need: the stored graph has 27 incoming calls, but its declared django/ scope contains seven. With `--path 'django/*' --context-lines 2 --format text --budget-bytes 12000`, current code returns all seven reviewed calls and matching excerpts from five source files in one 8,000-byte page. evals/archive-urlencode/context-verified.json records exact source/AST parity and an unchanged archive. This is a functional diagnostic on a preparation artifact; the frozen preparation runtime predates this filter, and no model has run against either version.

Tests check filtering before counting/pagination, same-line call multiplicity across offsets, target retention outside the pattern, case-sensitive matching, empty results and invalid patterns. Excluded caller files are deleted before the query to prove context retrieval does not read them. The initial fixture tried to create src and SRC directories on a case-insensitive filesystem and failed before querying. The corrected fixture uses distinct directory names and separately checks case-sensitive matching; initial-fixture-failure.txt retains the failure.

This reduces irrelevant retrieval for a scoped task; it does not establish model token savings or resolve the remaining JVM accuracy issues. Future model evaluation must freeze the validated current runtime at a new path, preserving the earlier preparation and failed model pairs.

Both parser environments pass 226 engine tests; the root suite passes 53. Clean wheel/ZIP installed CLI validation checks included and absent path patterns, matching edge counts, source context and no consumer index.
