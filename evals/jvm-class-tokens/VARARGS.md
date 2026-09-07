# Array arguments and generic varargs

Further compiler testing exposed a false edge introduced by the array support at 98c2eed. For `<T> T[] hit(T... values)` called with `new String[0]`, javac accepts a String[] result and rejects a String[][] result. Columbus instead rejected the former and accepted the latter because it treated the array as one vararg value before considering fixed-arity applicability. varargs-before.json preserves that failing 54-case observation, including compiler diagnostics and graph evidence.

When argument count matches parameter count, the resolver now first uses a compatible reference-array component for the generic vararg parameter. It applies this before checking result context. A fixed Class<T> anchor can make that interpretation inapplicable, in which case the array remains one variable-arity value. Primitive array components cannot instantiate T, so primitive arrays also remain reference values instead of being boxed elementwise.

The expanded 58-case compiler gate passes with both parser environments. It retains all prior cases and adds flat/nested result types, anchored array arguments, primitive array values and incompatible reference arrays. Both engine suites pass 229 tests; root tests pass 53. Clean wheel/ZIP verification passes against the changed runtime. The candidate platform workflow now runs verify_varargs.py; success of an older workflow does not validate this new change. No issue is closed on these bounded fixtures.

Separately, compare_spring.py froze runtimes at 9ebf60e and 98c2eed differing only in jvm.py, indexed the same 1,166 Spring files, checked every indexed source hash and compared complete edge tuples. All 31,408 edges and base syntax facts were equal. spring-array-comparison.json records that comparison. It covers the initial array support, not this later varargs correction, and is not compiler accuracy evidence for every Spring edge.

This corrects an observed false target rather than relabeling it as uncertain confidence. Broader Java inference, full-corpus precision, cross-platform results for this exact fix and actual model token savings remain separate requirements.


## Full Spring regression check after the varargs correction

The parameterized comparator also indexed Spring 4c8c6409a27a62ab163d3b6196ad862b7c835440 with frozen runtimes at 98c2eed and 29651dc. All 1,166 indexed file hashes match, and their canonical manifest SHA-256 is 53bd4243666ca2f8ad02a3f00b349dd565ac10f1df889e8041bc4c1b87753143. Base syntax and all 31,408 complete edge tuples are unchanged, with zero additions/removals. spring-varargs-comparison.json retains the source/runtime identities and comparison. This closes the prior full-corpus regression-check gap for this exact varargs change; it does not establish compiler correctness of every preexisting edge.

The earlier array implementation at 98c2eed passed all 13 candidate platform jobs in run 34169909637; array-platform.json retains those conclusions. The newer 29651dc candidate run 34170326885 was still in progress when this evidence was recorded. Continue polling that exact run rather than attributing the older success to the newer fix. No release or model trial was performed.

Follow-up: run 34170326885 completed successfully at 29651dc, with all 13 jobs passing across Linux, macOS and Windows, including the expanded compiler gate and aggregate installation/upgrade checks. varargs-platform.json records the exact revision and job conclusions. This supplies platform evidence for the varargs fix itself; it does not expand the bounded semantic coverage of the 58 compiler cases.
