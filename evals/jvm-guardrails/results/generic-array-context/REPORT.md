# Generic array result type identity

A follow-up compiler probe exposed a false call edge in the previous generic check: a source-declared `Object` was treated as bootstrap `java.lang.Object` when checking `Object result = hit("text")` for a generic array return. Javac rejects the assignment. Two valid assignments to `Cloneable` and `java.io.Serializable` were also omitted. [Before observation](before.json) deliberately records a failed gate.

The array result check now resolves the context type identity before accepting the three bootstrap array supertypes. Source-declared lookalikes stay distinct. The extended blocking gate preserves all previous 25 cases and adds six array contexts: both [pinned](pinned.json) and [candidate](candidate.json) pass all 31 cases. The two intentionally unsupported valid bounded/explicit-generic cases remain unresolved. Both engine suites pass 208 tests.

A fresh candidate-parser Spring index has identical full edge rows (31,408 across all kinds) and 1,166 source hashes compared with e8b494d. [Parity receipt](spring-parity.json). Therefore the preceding Spring coverage tradeoff remains unchanged; this patch does not demonstrate broader semantic completeness or token savings.

Reproduce with `PYTHONPATH=skills/columbus/scripts .venv/bin/python evals/jvm-guardrails/verify_generic_array_context.py <jdk-bin> <receipt.json>`; prepend the installed candidate runtime to PYTHONPATH for that variant. The workflow runs this extended gate. Hosted validation for this patch is pending.
