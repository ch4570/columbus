# Java enhanced-for iterable scope

Issue #4's DefaultResourceLoader gap includes the call getProtocolResolvers() in the enhanced-for iterable expression. The old extractor put the entire loop into an opaque scope, suppressing even that outer-scope call. Java evaluates the iterable before the loop variable exists; the extractor now visits that expression in its enclosing scope, then keeps the remaining loop content opaque.

The change does not resolve loop-variable receiver calls or infer iterable element types. A nested loop inside an opaque body remains conservative, including its iterable expression. Kotlin loops, ordinary for loops, lambdas and catch scopes are unchanged. Existing resolution/access/argument checks still apply to the newly exposed expressions.

The new unit failed before implementation and passes afterward. Four isolated compiler controls cover an implicit iterable call, parameter receiver, invalid argument, and nested loop. javac diagnostics and javap output are retained for both Java grammar environments. The existing 103-case compiler gate passes. Full engine suites pass 251 tests each; root tests pass 53; wheel/ZIP installation verification passes.

On the fixed Spring spring-core corpus (1,166 files), the prior base-absence index and fresh current index have identical source hashes and symbols. Eleven call edges are added and none removed. The added getResource:158 -> getProtocolResolvers declaration is directly source-reviewed: the getter returns the registered collection, and the loop obtains it before its body. protocolResolver.resolve at line 159 remains unresolved. Other added edges are listed in spring-diff.json but are not all independently source-reviewed or compiler-verified; eleven additions are not a corpus precision claim. No model trial or token-saving claim is made.

The broader loop-variable type-resolution and independent-corpus requirements remain open. This fixes the incorrect scope boundary without claiming completion of the entire issue or the model-efficiency goal.
