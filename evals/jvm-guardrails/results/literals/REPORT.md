# Primitive literal argument guard

2026-09-08 KST. Before asserting a sole Java callable target, the resolver now rejects recognized literals incompatible with primitive parameters. It permits primitive identity/widening and rejects method-invocation constant narrowing. Reference/null literals cannot match a primitive parameter, except that a sole final null may denote the array for a varargs parameter.

Fourteen cases match javac 17.0.20.1: eight invalid calls previously emitted targets and now remain unresolved; six valid cases retain their targets. Cases include boolean/integer mismatch, string/null to int, long to int, integer literal to byte, int to long, float to double, char to int, boolean identity, mixed primitive varargs, and null array versus null vararg element. Source, hashes, compiler diagnostics and before/after references are preserved in [summary.json](summary.json).

All 190 engine tests, compilation and diff checks passed locally. Reproduce with:

```sh
.venv/bin/python evals/jvm-guardrails/verify_literals.py /path/to/jdk/bin /tmp/literal-results
```

The guard intentionally does not infer expression, identifier, cast, reference-type, generic, boxing or cross-language applicability. Unknown argument types retain the existing heuristic behavior; this is not a complete proof that an emitted call compiles. Overloads and inherited candidate selection remain incomplete. The new records retain the recognized argument types to make the evidence inspectable. Decimal integers beyond supported signed ranges are left unknown rather than guessed.

This advances issue #8's false-edge gate but does not close it, change the shipped grammar, or establish token savings. Hosted platform/distribution and broader source-reviewed precision checks remain pending for the latest analyzer.
