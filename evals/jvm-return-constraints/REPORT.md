# Return-only generic constraints

The current audit reproduced false Java targets when a type variable occurs in a return type but no parameter. For example, `<T extends Number> T hit()` assigned to String is rejected by javac, yet the previous resolver emitted a call edge. The same problem occurs for `<T> T[] hit()` assigned to String and a declaring-class `T hit()` assigned to String. before.json preserves these compiler failures and resolved references using the frozen pre-change jvm.py from 1758c2a.

Generic constraint relevance now includes the return type as well as parameters. This applies existing conservative bound/declaring-type checks to return-only variables and checks generic array result context even when there are no value arguments. Unbounded return-only T and T[] retain supported valid contexts. Valid bounded and declaring-type cases remain unresolved because their substitution is not implemented; this is recorded explicitly in the gate rather than counted as full recall.

The expanded gate retains the previous 58 cases and adds seven return-only cases. All 65 pass with the pinned parser. The new engine regression covers wrong bounded/array contexts, valid unbounded contexts and declaring-type substitution. No claim is made about arbitrary generic return shapes, general inference or complete Spring precision. Full Spring comparison and platform results for this exact change remain pending.

initial-before.json retains an early observation whose analyzer hash was read after the file had been edited while the already-imported old module was still compiling fixtures. That hash cannot identify its loaded code. The authoritative before.json reruns the compiler gate against an immutable temporary copy of jvm.py from 1758c2a, so its reported hash identifies the executed analyzer. No initial observation was silently discarded.

No model trial or token-savings claim accompanies this correctness fix. The candidate platform workflow now uses the expanded 65-case entrypoint; an older successful run cannot validate it.

Final local validation: both pinned and candidate parsers pass all 65 compiler cases and each passes 231 engine tests; 53 root tests and newly built wheel/ZIP clean installation checks pass. Logs and distribution.json are retained here.

## Spring regression and coverage cost

The completed comparison freezes runtimes at 1758c2a and 6594992, differing only in jvm.py, on Spring 4c8c6409a27a62ab163d3b6196ad862b7c835440. All 1,166 indexed source hashes and base syntax facts match. Complete edge tuples change from 31,408 to 31,365: zero additions and 43 removals. spring-comparison.json retains the exact differences, runtime manifests and source-manifest hash.

Every removed edge was matched to its post-change unresolved reference and checked against source bytes. Forty now report unsupported bounds/explicit type arguments, and three report declaring-type substitution. spring-removed-review.json retains all 43 source lines, target signatures/excerpts, file hashes, result contexts and reasons. Fifteen involve toAnnotationSet(), seven firstDirectlyDeclared(), seven MergedAnnotation.missing(), and the remainder other generic factories or declaring-type returns.

These removals are a conservative coverage loss, not evidence that all 43 prior Spring calls were invalid. The reduced compiler cases prove the three concrete false-edge shapes; the full Spring comparison does not compile or independently prove each real call's applicability. In particular, 35 removed references have no extracted expected_type; absence of that fact cannot prove that the enclosing expression imposes no constraints. Restoring such edges indiscriminately would repeat the earlier missing-constraint assumption. More precise enclosing-expression and substitution evidence is needed to regain this coverage reliably.

At the latest poll, the exact 6594992 ordinary distribution run 34172560093 has four successful Linux/macOS jobs and two Windows jobs still running. Candidate run 34172560092 has six initial jobs running. These specific runs remain pending; no duplicate dispatch or all-platform success claim was made.
