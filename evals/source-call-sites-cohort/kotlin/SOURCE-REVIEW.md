# Kotlin-to-Java property lookup: prospective source rubric

This is a source-reviewed development comparison. It reuses the underlying measured property-resolution operation; the Kotlin entry surface does not make the Java mechanism held-out. No models, upstream code, tests or builds were run for this review. All 5 findings and 19 zero-based criterion clauses in `criteria.json` are required. Shared answer evidence, including complete quoted implementation, may support clauses outside a finding's representative quote. Contradictory prose fails the affected clause. Each finding needs a cited range of at most 40 physical lines containing its private marker. Its quote may be a contiguous subrange inside that citation: matching ignores indentation only, with no stitching, and does not separately require the quote itself to contain the marker. Paths, markers and this rubric are not supplied as a navigation oracle in the user question.

## Source identity and scope

The existing full `spring-core/` module fixture includes all 1,166 source files and both languages, not convenient Kotlin-only snippets or the entire multi-module repository. ZIP SHA256: `68572527bfad750c2ab2c55dcbab1324568a4584d0d122cc3a4dfac8c139bd0c`. Complete ZIP/local source inventory equality was reverified; its canonical inventory SHA256 is `53bd4243666ca2f8ad02a3f00b349dd565ac10f1df889e8041bc4c1b87753143`.

Upstream pin: [Spring Framework 4c8c6409a27a62ab163d3b6196ad862b7c835440, spring-core](https://github.com/spring-projects/spring-framework/tree/4c8c6409a27a62ab163d3b6196ad862b7c835440/spring-core). `../sources.json` records archive/root paths, exact inventory encoding, historical retrieval limits, and Apache-2.0 licensing. Source headers remain present; the repository-root standalone license is outside this module ZIP.

| Full module-relative production path | Bytes / physical lines | Raw SHA256 |
| --- | --- | --- |
| `src/main/kotlin/org/springframework/core/env/PropertyResolverExtensions.kt` | 1873 / 61 | `9b1691b4ae7034edd9749f4ee7cba10dcf854a01b7dfd7c506ffc62481b852fe` |
| `src/main/java/org/springframework/core/env/PropertySourcesPropertyResolver.java` | 4020 / 121 | `d11b2a0c42664718808ca6383360717edcb337f0614c9bb64a8600f7372fc67c` |
| `src/main/java/org/springframework/core/env/AbstractPropertyResolver.java` | 13513 / 378 | `bf33323681de132b1694eb0ca0d5c1582f5584a9d05153cc6e79fb5b0ad6f965` |
| `src/main/java/org/springframework/util/PropertyPlaceholderHelper.java` | 4538 / 114 | `f7f7c29b36df44464353008b8831fc1c8c7170cc3097e10e5d78d6f12ef29ce1` |

## Clause-to-source review

`kotlin_lookup_handoffs`, representative `PropertyResolverExtensions.kt:40–61` (22 lines; marker at 50):

- [0] Line 30 is `operator fun PropertyResolver.get(key: String): String? = getProperty(key)`; it is the nullable String operator, not another generic search.
- [1] Lines 40–41,50–51,60–61 spell all inline/reified `T : Any` forms, return types and Java-class/default/required arguments.
- [2] These bodies only delegate. `T::class.java` passes a Java Class, not a recursive generic-type descriptor; the Java implementation owns lookup and failures. Explaining this boundary does not require Kotlin compiler internals or a concrete primitive-boxing example.

`ordered_property_lookup`, representative `PropertySourcesPropertyResolver.java:73–100` (28 lines; marker at 92):

- [0] Lines 59–70 select String/typed nested=true versus raw String nested=false. The raw route still reaches conversion at 92.
- [1] Lines 74–81,93–99 establish supplied collection order, raw null continuation and null result when sources/values are absent.
- [2] Lines 81–92 process the first non-null raw value and directly return conversion. No null-conversion continuation or error-catching retry is present; a source throw also escapes the loop.
- [3] The complete method reads sources afresh on every call, without a resolved-value cache. It does not promise thread-safe concurrent mutation, which is out of scope.

`nested_placeholder_policy`, representative `AbstractPropertyResolver.java:272–287` (16 lines; marker at 286):

- [0] `PropertySourcesPropertyResolver.java:82–92` checks String unconditionally, or other CharSequence only for exact String/CharSequence targets, before conversion. The raw flag disables these branches.
- [1] `AbstractPropertyResolver.java:94,173–184,272–277` establishes the default strict flag, configuration, empty-string return and selected nested policy. This is unresolved-text policy, not a signal to continue at another source.
- [2] Lines 245–257 choose and lazily retain independent non-strict/strict helpers, ignoring the nested flag for direct calls. Lines 280–282 pass the settings and boolean into construction.
- [3] Lines 285–286 pass `this::getPropertyAsRawString` to helper replacement. `PropertyPlaceholderHelper.java:64–71,94–96` forwards construction and replacement to its parser. This criterion stops at that actual handoff; it neither demands a parser-grammar tour nor claims the raw callback prevents all recursion inside the parser.

`property_conversion_service`, representative `AbstractPropertyResolver.java:298–312` (15 lines; marker at 309):

- [0] Lines 299–307 establish the null-target return and assignability fast path inside the null-instance-service branch.
- [1] Lines 302–311 choose shared fallback when necessary versus the stored service. A stored service is not bypassed simply because the value was assignable.
- [2] Lines 108–127 distinguish the synchronized/double-checked creation of an independent instance service from the shared fallback and show setter null rejection. The getter's stored result affects later selection at 302.
- [3] The conversion call returns directly with no retry, null replacement or exception catch. A generic return signature is not a conversion-success proof.

`default_required_outcomes`, representative `AbstractPropertyResolver.java:220–242` (23 lines; marker at 237):

- [0] Lines 215–223 implement String/typed defaults after normal lookup; the non-null result wins and the null result gets the caller's default.
- [1] Lines 227–241 perform required lookup and throw `IllegalStateException` only for the returned null. `validateRequiredProperties` and its aggregate exception are deliberately excluded.
- [2] The wrapper null check combined with the concrete loop's direct return at `PropertySourcesPropertyResolver.java:92` covers a null conversion result without a later-source restart. Raw null at line 81 is a different branch.
- [3] None of these wrapper bodies catches source, placeholder or conversion exceptions. Therefore default-valued and required calls do not universally swallow or replace earlier failures.

## Read-only corroboration and scope boundaries

The following test bodies were inspected, never executed:

- `src/test/kotlin/org/springframework/core/env/PropertyResolverExtensionsKotlinTests.kt`: 2045 bytes / 62 physical lines; SHA256 `a955d5e523d52bd448c4eee82b849aac37292493cafdcc50f6dc2b2d03046d3f`. Its four mock-based tests verify operator and exact overload delegation, not the complete real-source pipeline.
- `src/test/java/org/springframework/core/env/PropertySourcesPropertyResolverTests.java`: 15733 bytes / 395 physical lines; SHA256 `8e22ef0ad85ff1cc91edfef2cb37c0991bd9d4fe4f8062ac9162cf4a53cef089`. Inspected source-order, null/default/required, nonconvertible, non-caching, CharSequence and strict/permissive nested-placeholder tests corroborate the implementation. Tests are not a separate dynamic success claim.

The visible descriptions ask every scored distinction, including null conversion versus exceptions and the getter's service side effect. No hidden requirement enumerates every converter, parser escape/default/cycle grammar, environment setup, containsProperty or required-key aggregation. An equivalent explanation need not reproduce exact exception messages.

## Reuse, graph feasibility and selection bias

`evals/multilang-token-batch/java/cases.json:6` already measured source order, default/required null policy, raw/nested placeholders, service selection and processing failure boundaries in these exact Java implementation classes. The Kotlin extensions provide an additional entry surface but do not make those underlying mechanisms new. The module and operation are reused development data, and no historical answer, rubric or outcome is replaced or regraded.

Prior graph inspection found all four Kotlin extension-to-Java call references unresolved because extension receiver dispatch is unsupported. That limitation must remain visible; source is sufficient to explain the handoff, but an unresolved reference is not a delivered resolved relationship. Potential useful downstream Java source calls include helper construction at `AbstractPropertyResolver.java:281–282` and `DefaultConversionService.getSharedInstance` at 309. These are review candidates only, not a preselected acceptance list. The actual new pinned graph must be reviewed separately, including all relevant emitted relationships rather than selecting only a convenient successful edge. Class-node constructor edges and heuristic call resolution do not prove runtime execution.

This case tests Kotlin-to-Java exploration, not isolated Kotlin graph coverage. Selection followed prior source/graph inspection and is biased toward known mechanisms; downstream Java edge delivery must not be reported as resolved Kotlin dispatch. Optional call-site/source output is not required in the neutral question. Source quotations alone are not graph-relationship evidence; actual input and output token gates, all repetitions and full quality remain separate requirements, not consequences of shorter tool payloads.
