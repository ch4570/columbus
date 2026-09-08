# Kotlin and Java analysis contract

Use genuine Tree-sitter grammars pinned in `scripts/requirements.txt`. Kotlin `.kt`/`.kts` and Java `.java` are primary; the Python AST adapter remains available. A grammar may still reject valid constructs or handle incomplete code differently from a compiler.

The JVM adapter extracts packages/imports and supported class, interface, object, function, method, property, and constructor declarations from syntax nodes. It retains spans, signatures, hierarchy, and unresolved references. Overloads retain separate IDs. Inspect symbols/diagnostics rather than assuming every Kotlin feature is represented.

| Evidence | Meaning |
|---|---|
| `syntactic` | Direct declaration/containment fact |
| `heuristic` | Candidate from package/import/type/scope facts |
| `resolved_static` | Existing Python name-resolution result, still not runtime proof |
| Unresolved/partial | Insufficient or invalid syntax; inspect source |

JVM calls remain candidates. The adapter does not implement compiler overload resolution, generic inference, runtime dispatch, Kotlin extension selection, coroutine semantics, annotation processing, or Spring bean selection. Mixed-language links require explicit supporting facts; equal last names alone must not create global calls.

Type lookup keeps class/method type parameters and nested declarations in a separate lexical type namespace. A type parameter receiver stays unresolved with a bound/applicability reason; it must not link to a same-named concrete class. Calls on types with explicit inheritance stay unresolved until inherited candidates and argument applicability are supported, even if the subclass declares only one matching name. This deliberately reduces coverage. Inspect source for the actual route.

Java type-name receivers require static methods; typed value receivers remain separate, including values whose names match a class. Known String/boxed-literal conversions are checked against supported reference types. Wildcard-import and other unknown reference conversions remain unresolved; this is not full argument type inference.

For unbounded method type parameters, the adapter checks correlated `Class<T>`, single invariant `Container<T>`, and bare `T`/`T...` arguments using literals, supported typed values, and limited standard `valueOf` expressions. Direct variable/return contexts constrain supported `T`/`T[]` results. Bounds, explicit type arguments, declaring-type substitution, complex generic shapes, and unknown expressions remain unresolved. These checks do not implement complete Java inference or prove invocation validity.

Java accessibility checks cover the selected declaration and its enclosing types: private nestmates, package identity, and implicitly public interface members. Cross-package protected access stays unresolved pending subtype/receiver analysis; this is not a complete Java module/classpath accessibility check.

Context and relationship responses expose `semantic_complete=false`, repository diagnostic/unresolved counts, and partial node counts separately from output `truncated`. Repository counts are global, not a per-symbol completeness proof. A clean parse still does not imply complete call resolution.

Build `.kts` syntax is not a resolved Gradle dependency graph. Build/config files are freshness inputs and are never executed. Duplicate fully qualified symbols across modules may remain ambiguous because source-set classpaths are not resolved. Index the repository root to include main/test sources across modules unless scope restriction is requested.

SCIP import and live language-server integration are possible next layers, not current features. scip-java covers Java and Kotlin, but Kotlin is less mature and automatic Gradle support does not imply automatic Maven/Android Kotlin support. It may compile projects, so do not run it implicitly during syntax queries. [scip-java guide](https://github.com/scip-code/scip-java/blob/main/docs/getting-started.md).

Spring endpoint, Kafka topic, and SQL table edges are future adapters. Annotation metadata alone is not implementation of these relationships. Dynamic wiring needs candidate labels or runtime evidence.

The parser does not invoke LLMs or execute target code. Exclusions are not secret detection. Treat DB/export/source responses with the same sensitivity as the repository.

Java enhanced-for iterable expressions are evaluated in the enclosing scope, before the loop variable binding. Their calls use the ordinary declaration resolver. The loop body still has an opaque scope: loop-variable calls and nested iterable expressions inside that body remain unresolved. This does not infer collection element types or runtime dispatch.
