# Conditional result context

The enclosing-expression audit showed that missing result context included conditional branches. Reduced javac cases reproduce three false targets: incompatible generic values in an assignment branch, return branch and nested parenthesized branch. before.json retains those failures from the unchanged pre-fix analyzer.

Java invocation context now traverses parentheses and the consequence/alternative branches of ternary expressions before looking for a variable declaration or return type. It does not propagate the result type into the condition expression. This feeds the existing generic result checks; it does not implement argument-position inference, overload selection or bounded type substitution.

verify.py retains the prior 65 cases and adds six compiler cases. The three invalid cases must remain unresolved; valid Integer branches and a Boolean-producing condition retain their calls. The new engine regression also checks the extracted expected_type, including its absence on the condition. This is not evidence for arbitrary numeric conditional typing or complete Java inference.

No model experiment was run. This change improves the evidence available for the remaining JVM work; it does not establish actual token savings or restore the 43 Spring edges previously suppressed by unsupported generic constraints. A full Spring comparison of this exact change remains separate.

Final validation: both parser environments pass all 71 compiler cases and 232 engine tests. With file mutations stopped, 53 root tests and newly built wheel/ZIP installation verification pass. The first root run failed a two-build ZIP hash equality check while evaluation files were being added concurrently; initial-root-failure.txt preserves it. That timing overlap is a plausible cause, not a separately isolated causal proof. No implementation was changed to make the second run pass.
