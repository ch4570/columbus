# Conditional result context

The enclosing-expression audit showed that missing result context included conditional branches. Reduced javac cases reproduce three false targets: incompatible generic values in an assignment branch, return branch and nested parenthesized branch. before.json retains those failures from the unchanged pre-fix analyzer.

Java invocation context now traverses parentheses and the consequence/alternative branches of ternary expressions before looking for a variable declaration or return type. It does not propagate the result type into the condition expression. This feeds the existing generic result checks; it does not implement argument-position inference, overload selection or bounded type substitution.

verify.py retains the prior 65 cases and adds six compiler cases. The three invalid cases must remain unresolved; valid Integer branches and a Boolean-producing condition retain their calls. The new engine regression also checks the extracted expected_type, including its absence on the condition. This is not evidence for arbitrary numeric conditional typing or complete Java inference.

No model experiment was run. This change improves the evidence available for the remaining JVM work; it does not establish actual token savings or restore the 43 Spring edges previously suppressed by unsupported generic constraints. A full Spring comparison of this exact change remains separate.

Final validation: both parser environments pass all 71 compiler cases and 232 engine tests. With file mutations stopped, 53 root tests and newly built wheel/ZIP installation verification pass. The first root run failed a two-build ZIP hash equality check while evaluation files were being added concurrently; initial-root-failure.txt preserves it. That timing overlap is a plausible cause, not a separately isolated causal proof. No implementation was changed to make the second run pass.

## Completed Spring comparison

The initial comparator stopped at its base-syntax equality assertion because it did not allow the intended expected_type additions. initial-spring-comparison-failure.txt preserves that failure. Both frozen indexes had already completed, so compare_saved.py inspects those same databases without reindexing, checks all 1,166 current source hashes, and verifies every runtime file against commits 6594992 and cf635cf.

Exactly 307 references gain a previously empty expected_type. Every other parsed field and all 31,365 complete edge tuples remain equal. spring-comparison.json retains all new contexts and both runtime manifests. The source-manifest hash remains 53bd4243666ca2f8ad02a3f00b349dd565ac10f1df889e8041bc4c1b87753143. This proves the bounded extraction change has no edge regression on this corpus, not that every extracted context or preexisting edge is compiler-correct. It does not regain unsupported generic-bound coverage.

The exact cf635cf distribution run 34173030266 and candidate run 34173030244 were in progress at the latest poll. The earlier 6594992 candidate success is recorded separately and is not attributed to this newer change.
