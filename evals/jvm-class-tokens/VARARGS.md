# Array arguments and generic varargs

Further compiler testing exposed a false edge introduced by the array support at 98c2eed. For `<T> T[] hit(T... values)` called with `new String[0]`, javac accepts a String[] result and rejects a String[][] result. Columbus instead rejected the former and accepted the latter because it treated the array as one vararg value before considering fixed-arity applicability. varargs-before.json preserves that failing 54-case observation, including compiler diagnostics and graph evidence.

When argument count matches parameter count, the resolver now first uses a compatible reference-array component for the generic vararg parameter. It applies this before checking result context. A fixed Class<T> anchor can make that interpretation inapplicable, in which case the array remains one variable-arity value. Primitive array components cannot instantiate T, so primitive arrays also remain reference values instead of being boxed elementwise.

The expanded 58-case compiler gate passes with both parser environments. It retains all prior cases and adds flat/nested result types, anchored array arguments, primitive array values and incompatible reference arrays. Both engine suites pass 229 tests; root tests pass 53. Clean wheel/ZIP verification passes against the changed runtime. The candidate platform workflow now runs verify_varargs.py; success of an older workflow does not validate this new change. No issue is closed on these bounded fixtures.

Separately, compare_spring.py froze runtimes at 9ebf60e and 98c2eed differing only in jvm.py, indexed the same 1,166 Spring files, checked every indexed source hash and compared complete edge tuples. All 31,408 edges and base syntax facts were equal. spring-array-comparison.json records that comparison. It covers the initial array support, not this later varargs correction, and is not compiler accuracy evidence for every Spring edge.

This corrects an observed false target rather than relabeling it as uncertain confidence. Broader Java inference, full-corpus precision, cross-platform results for this exact fix and actual model token savings remain separate requirements.
