# Java type receivers and literal reference arguments

The old resolver classified the same `T.hit()` differently depending on file layout. A lexical class in the same file was mistaken for an unknown value binding, suppressing valid static calls. A type found across files could resolve an invalid instance call. `before.json` retains the first ten compiler fixtures; `before-expanded.json` reruns the final twenty-four fixtures against an isolated copy of the `f6a7530` JVM analyzer.

The correction distinguishes lexical class declarations from typed values and re-enters the type namespace so nearer type parameters still shadow class names. Type receivers require static methods. A value named `T` with declared type `T` continues to permit instance calls. Java class names in ordinary method-call syntax are rejected rather than treated as callable functions.

Restoring static calls exposed a further unsafe edge: passing an integer literal to `hit(String)`. The correction therefore also checks known String and boxing/reference conversions, including simple/qualified standard types, declared-type shadowing and explicit imports. For classified literal arguments, unsupported or ambiguous reference conversions remain unresolved. The distinction between invocation conversion and arbitrary string conversion follows [JLS 5.3](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.3). This is not full expression typing, generic inference or overload applicability.

On the final twenty-four literal javac fixtures:

| Result | Before | After |
| --- | ---: | ---: |
| Compiler-invalid selected calls emitted | 2 / 12 | 0 / 12 |
| Compiler-valid selected calls resolved | 2 / 12 | 11 / 12 |
| Valid inherited static call unresolved | 1 | 1 |

Both pinned Java 0.23.5 and candidate 0.23.5+columbus.1 produce the corrected result with javac 17.0.20.1. Sources, compiler diagnostics, reference targets, source/analyzer hashes and parser versions are preserved in the JSON receipts. Target builds, processors and runtime code were not executed; javac used `-proc:none` on generated literal fixtures only.

Both final engine suites passed 206 tests. Root tests passed 53 during this change, and the skill validator passed. The prior sixteen package-access and twenty access/static-context fixtures also passed during integration. The new compiler gate is part of each candidate platform job. Fixture directory names were made filename-safe before CI. The shared compiler verifier now hashes the actually imported parser module, allowing the old-analyzer replay to retain the correct provenance.

This improves positive coverage while removing observed false edges; it does not establish broad precision on a real project. Inherited candidate sets, nonliteral argument typing, generic/wildcard conversions, constructor applicability and runtime dispatch remain incomplete. Issue #8 and the token-saving goal remain open. No model token experiment was rerun for this change.

Commit `9a249be870ffc088e226b0541d2f8c08f15fd99d` was pushed. Its [ordinary distribution](https://github.com/ch4570/columbus/actions/runs/34153270568) and [candidate/aggregate distribution](https://github.com/ch4570/columbus/actions/runs/34153270616) runs were confirmed in progress. Cross-platform success for this commit remains pending.

Both hosted runs subsequently completed successfully at `9a249be`: six ordinary jobs and thirteen candidate/aggregate jobs (`platform/production.json`, `platform/candidate.json`). A subsequent [real Spring audit](../../../spring-core/results/type-receiver-review/REPORT.md) found 42 added and 32 removed calls and exposed generic nonliteral-argument false edges beyond this fixture set. The successful CI must not be interpreted as closing that remaining correctness gap.
