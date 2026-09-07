# Scalar literals passed to Java array parameters

The compiler-backed probe found six false call targets in baseline `9d190fa`: scalar integer, boolean, character, string and floating literals passed to array parameters (including an array-valued varargs element). All six calls fail javac 17 but previously linked to the sole method candidate.

The resolver now rejects known scalar literals when the applicable parameter syntax denotes an array. Primitive boxing cannot create an array, and a string literal is not an array. Null and unknown expressions remain eligible; varargs element types are examined after removing the ellipsis. This is a negative applicability guard, not general array assignability or overload resolution.

Across the 12 prelisted cases, false targets decreased **6 → 0** and **all six valid targets were retained**, including null arrays, empty varargs, two null array elements, boxed Object varargs, and an explicitly cast array. Full source, source hashes, baseline/current references, compiler diagnostics and current analyzer hash are retained in [summary.json](summary.json).

Reproduce from the repository root:

```sh
PYTHONPATH=skills/columbus/scripts .venv/bin/python evals/jvm-guardrails/verify_arrays.py /path/to/jdk/bin /tmp/array-guard-results
```

The complete engine suite passes 192 tests with each of the pinned Java grammar and the separately installed `0.23.5+columbus.1` candidate. The corpus is deliberately small and compiler-backed; it does not establish broad repository precision, accessibility, generic inference, array-valued expression types, or Kotlin applicability. Those remain explicit goal gates.
