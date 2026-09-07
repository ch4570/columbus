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

Build `.kts` syntax is not a resolved Gradle dependency graph. Build/config files are freshness inputs and are never executed. Duplicate fully qualified symbols across modules may remain ambiguous because source-set classpaths are not resolved. Index the repository root to include main/test sources across modules unless scope restriction is requested.

SCIP import and live language-server integration are possible next layers, not current features. scip-java covers Java and Kotlin, but Kotlin is less mature and automatic Gradle support does not imply automatic Maven/Android Kotlin support. It may compile projects, so do not run it implicitly during syntax queries. [scip-java guide](https://github.com/scip-code/scip-java/blob/main/docs/getting-started.md).

Spring endpoint, Kafka topic, and SQL table edges are future adapters. Annotation metadata alone is not implementation of these relationships. Dynamic wiring needs candidate labels or runtime evidence.

The parser does not invoke LLMs or execute target code. Exclusions are not secret detection. Treat DB/export/source responses with the same sensitivity as the repository.
