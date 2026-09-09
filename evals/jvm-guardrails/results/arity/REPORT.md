# Java argument-count guard

2026-09-08 KST. The resolver previously emitted a sole method candidate even when the call supplied an impossible number of arguments. Java AST calls now retain `argument_count`; comments do not contribute. For a Java declaration, fixed parameters require equal counts and varargs require at least the fixed prefix count. Incompatible calls stay unresolved with a specific reason.

Seven cases were compared with javac 17, with annotation processing disabled. Four invalid calls previously emitted targets and now remain unresolved. Three valid cases retain their targets, covering a comment in the argument list, zero varargs, and multiple varargs after a fixed parameter. Raw source, hashes, compiler exit/diagnostics and before/after references are in [summary.json](summary.json). The same seven cases are a regression in `test_jvm.py`.

All 189 engine tests and compilation passed locally. This is an arity guard, not argument-type applicability or overload resolution. It applies only to Java-to-Java callable declarations; Kotlin defaults/named arguments and cross-language rules are not inferred from Java arity. Constructor/class candidate behavior is unchanged. Inherited overloads, type compatibility and broader compiler accuracy remain unfinished under issue #8. This does not establish model-token savings or complete the overall goal.
