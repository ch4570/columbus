# JVM false-edge guardrails: issue #8 progress

2026-09-08 KST. The two concrete issue #8 false targets are blocked. This does not close the broader compiler-resolution requirement or claim full JVM precision.

| Fixture | Previous target | Compiler evidence | Current result |
| --- | --- | --- | --- |
| `Generic<T extends API>.run(T)` invokes `item.hit()` | unrelated concrete `T.hit()` | `invokeinterface API.hit:()V` | unresolved: type parameter bound/applicability required |
| `Inherited extends Base` declares `hit(String)` and invokes `hit(1)` | `Inherited.hit(String)` | `invokevirtual hit:(I)V`; the fixture's sole int declaration is `Base.hit(int)` | unresolved: inherited candidate/applicability required |

The harness compiles only the checked-in minimal fixtures with annotation processing disabled. It retains javap output, raw before/after references and call edges, source hashes, engine hash and dependency/compiler versions in [results](results/summary.json). Javac 17.0.20.1 passed both checks. Source rules: [JLS type/name shadowing](https://docs.oracle.com/javase/specs/jls/se25/html/jls-6.html#jls-6.4.1) and [method applicability](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12.2). These are declaration-target checks, not runtime-target enumeration.

The parser now stores a separate lexical type namespace for class/method type parameters and nested type declarations. Receiver type lookup honors this namespace before imports/package lookup. Class/method/outer generic cases cannot resolve to an unrelated concrete type with the same name. A positive regression verifies a nested class type despite a same-named value parameter. Existing package, alias, overload, and mixed Java/Kotlin tests continue to pass.

For types with explicit inheritance, method calls remain unresolved until inherited candidate sets and argument applicability can be established. This is conservative and suppresses some valid calls. It does not implement generic-bound dispatch, inherited overload selection, implicit Object member resolution, or compiler-equivalent namespace/accessibility rules. A sole syntax candidate without inheritance still has heuristic status; broader false-positive evaluation remains necessary.

Bounded context/map output now includes repository diagnostic and unresolved counts, semantic incompleteness and selected partial-node counts in both JSON and text. Neighbors exposes diagnostic counts alongside its existing semantic/traversal distinction. `truncated=false` only means the requested traversal/output fit. Counts are global and are not a local absence-of-edges proof. A 2,048-byte context regression preserves the partial node and these counters within the serialized budget.

Validation: 185 engine tests and 49 root tests passed locally. The new JVM gate failed on the prior implementation and passed after the fix; before/after logs are retained. Compilation and skill quick_validate passed. Full release wheel/ZIP and hosted platform validation remain outstanding for this combined worktree. The previous storage results identify their historical engine SHA; they are not final performance measurements of the new resolver.

Reproduce from repository root:

```sh
.venv/bin/python evals/jvm-guardrails/verify.py /path/to/jdk/bin
```

Remaining issue #8 work includes broader namespace/accessibility cases, argument applicability, independently reviewed precision/coverage beyond these two compiler fixtures, and separating retrieval candidates from static/runtime targets across the API. Issue #4 grammar evaluation, #6 further storage/output reduction and actual model-token comparison also remain active.
