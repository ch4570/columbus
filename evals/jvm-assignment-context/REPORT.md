# Java assignment result context

Issue #8 requires rejecting false call targets rather than relying on a heuristic label. On base 8c47f99, `String value; value=hit(1);` with `<T> T hit(T value)` was connected despite javac rejecting the invocation's incompatible result type. Declaration initializers and returns already carried expected types; ordinary assignments did not.

The parser now reads the type of an identifier on the left of plain Java `=` when the call is its result expression (including parentheses and conditional result branches). It searches enclosing lexical blocks and method parameters, retaining trailing array dimensions and varargs dimensions. Completed sibling-block declarations are excluded. Conditional conditions and compound assignments do not inherit the assignment's result type. Field/member/array-element targets and inferred `var` typing are not newly resolved; full generic inference remains unsupported.

The expanded compiler gate contains 84 cases: the prior 71 plus 13 assignment and control cases. The frozen base runtime emits six wrong edges in this corpus; the final implementation removes all six. Ordinary and candidate Java grammar environments pass all 84 expected outcomes, including the corpus's explicitly conservative unresolved valid cases. Raw compiler diagnostics, source hashes, versions and reference/edge traces are retained in before-final.json, after-final.json and candidate-final.json. The base analyzer hash was checked against git 8c47f99 and final analyzer hash against the tested source.

Initial 81-case observations are retained as before/after/candidate.json. Those passed after the first edit but did not cover trailing-dimension parameters. A follow-up probe exposed that missing dimension handling; final code and the 84-case gate correct it. An earlier green bounded gate was not sufficient evidence for that syntax.

Both full engine environments passed 235 tests, root suite passed 53, and fresh wheel/ZIP distribution verification passed. The candidate CI workflow now runs this expanded gate. Remote CI for this commit and full Spring graph before/after evaluation remain pending; these bounded results are not a repository-wide precision/coverage claim or a model token savings result.

## Full Spring comparison

Git-frozen runtimes at 8c47f99 and 7bb9066 differ only in columbus/jvm.py. Both independently indexed the same 1166 Spring core files at source revision 4c8c6409a27a62ab163d3b6196ad862b7c835440; source manifest SHA256 is 53bd4243666ca2f8ad02a3f00b349dd565ac10f1df889e8041bc4c1b87753143.

With ordinary Java grammar 0.23.5, all 30512 complete edge tuples are identical. With candidate 0.23.5+columbus.1, all 31365 edge tuples are identical. Each environment extracts 772 additional expected_type contexts. audit_saved.py checks every complete parsed field after restoring only those expected_type values, as well as all source hashes and all runtime file hashes against the specified git revisions. No other parsed fields differ. The two grammar environments are reported separately; their edge counts must not be compared as if they were the same parser.

spring-ordinary-audit.json and spring-candidate-audit.json retain every changed context and runtime manifest. The comparison files retain fingerprints, source identity and zero added/removed edges. The ordinary comparison was initially produced before parser-version metadata was added to the script; its separate parser-version receipt records the unchanged local environment. The candidate comparison includes that metadata directly.

This source-corpus comparison found no additional lost or gained edges from the assignment fix. It does not prove all existing Spring targets correct, recover prior conservative omissions, or compile Spring. The independent 84-case compiler gate remains the evidence for the six concrete invalid-call shapes. Actual model token savings remain unproven.

At the retained observation, exact-commit ordinary run 34176266780 and candidate run 34176266809 are both in progress. Their final platform conclusions remain pending.

Follow-up: ordinary distribution run 34176266780 completed successfully in all six jobs at 7bb9066; platform-final.json retains the result. Candidate run 34176266809 remained in progress at that observation.
