# v1.1.0 release candidate evaluation

The fixed multilingual gate passes 21/21 cases on the current candidate. It covers 13 programming languages plus text fallback, including JSX/TSX variants; this is not a measurement of whole-language precision or actual model efficiency. The required pass rate is 100%, with no waived failures. [Raw results](multilang.json) include each source, source hash, runtime hashes, fidelity, call counts, archive hashes and incremental/fresh parity.

| Check | Local result | Evidence |
| --- | --- | --- |
| Engine, ordinary Java parser | 259 passed | [log](engine.txt) |
| Engine, experimental Java parser | 259 passed | [log](candidate-engine.txt) |
| Bootstrap, packaging and installer tests | 53 passed | [log](root.txt) |
| Multilingual contracts | 21/21 passed | [receipt](multilang.json) |
| Existing JVM compiler controls | 103/103 passed | [receipt](compiler.json) |
| Java `this` applicability controls | Two valid targets retained; invalid target rejected | [receipt](this-controls.json) |

The release evaluation found JSX literal text creating false calls and declarations. The fix masks recognized markup and literal children while retaining supported braced JavaScript expressions. Follow-up controls exposed three regressions: constrained TSX generic arrows with and without a return-type annotation mistaken for JSX, and a regex brace after `&&` prematurely ending an embedded expression. The original generic-arrow and regex controls failed before correction ([retained results](initial-regressions.json)) and the annotated form has a separate [before-fix receipt](return-type-before.json). All three pass in the final fixed suite. Existing TypeScript generics/comparisons and nested expressions are also covered by engine regressions.

This remains a lexical JSX heuristic, not a complete JSX/TypeScript parser. Unsupported forms, including JSX after `await` and generic JSX components, can still produce incomplete or incorrect facts. Python, Java and Kotlin use AST parsers; other tested profiles declare heuristic fidelity, and the unknown extension declares text fidelity with no code facts. gzip and XZ preserve the entire node/edge sets for each sample, saved lookup/callers/source work, and a one-file edit produces the same graph as a fresh index.

Local validation uses macOS and Python 3.11. The distribution workflow now runs this fixed multilingual gate in every Ubuntu/macOS/Windows × Python 3.11/3.14 job, alongside wheel/ZIP installation, relocation, archive, harness and pre-commit checks. Final PR checks and eventual tag checks are separate evidence: no earlier green run substitutes for the final commit. See [PR #12](https://github.com/ch4570/columbus/pull/12) for those checks and installation results.

Versions in the package, skill bundle and release installer are 1.1.0. The ordinary release continues to use upstream `tree-sitter-java==0.23.5`; passing the separate experimental-parser suite does not make that candidate the published default.

Actual model-token savings remain unproven: none of the [eleven recent comparisons](../model-usage-overview/REPORT.md) meets the unchanged quality-preserving input/output reduction gate. No additional model experiment was run for this release evaluation. The user has confirmed actual model-token savings are mandatory; [PLAN.md](PLAN.md) records that release criterion. These local functional results do not satisfy the conditional merge/release threshold.

Reproduce the multilingual gate from the repository root:

```sh
PYTHONPATH=skills/columbus/scripts python evals/release-v1.1.0/verify_multilang.py --output /tmp/columbus-multilang.json
```
