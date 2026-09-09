# Correlated Java generic arguments

The resolver now retains compact argument/type-context facts and checks supported unbounded method type variables across `Class<T>`, a single invariant container type argument, and `T`/`T...` values. This fixes the eight reduced observations from the preceding Spring audit, including invalid nonliteral calls previously linked and valid calls previously omitted. Source declarations retain distinct identities from bootstrap Java types.

Both [pinned](pinned.json) and [candidate](candidate.json) parser receipts pass all 25 generated javac cases (JDK 17.0.20.1, annotation processing disabled). Valid bounded and explicitly typed calls intentionally remain unresolved. These finite fixtures do not establish complete Java invocation validity. The candidate workflow now runs this blocking gate.

Final engine suites pass 208 tests in each environment; the root suite passes 53. The skill validator passes. Old argument facts without the new evidence remain unresolved until reparsed; analyzer hashing invalidates prior caches.

Bounds, explicit type arguments, declaring-type substitution, arbitrary expression typing, complex generic shapes, overload resolution and general subtype reasoning remain incomplete. Result context handling covers only supported direct declarations/returns. All stored JVM call matches remain heuristic and runtime dispatch is unverified.

The [same-source Spring comparison](../../../spring-core/results/generic-constraints/REPORT.md) restores all 32 previously removed calls, but moves 207 existing calls to unresolved. This is a coverage tradeoff, not proof that those 207 calls were invalid. No actual model trial or token-savings claim accompanies this change. Hosted checks are pending the code push.
