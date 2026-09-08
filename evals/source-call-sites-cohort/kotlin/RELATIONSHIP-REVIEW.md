# Kotlin property navigation: reviewed stored relationships

This private, prelaunch catalog supplements the unchanged 5 findings and 19 clauses in `cases.json`, `criteria.json` and `SOURCE-REVIEW.md`. Its **8** entries are useful actual Java implementation edges downstream of the Kotlin entry surface. They must not be reported as eight resolved Kotlin calls, a complete lookup pipeline or observed model usage.

## Bound inputs and review method

- Upstream: Spring Framework `4c8c6409a27a62ab163d3b6196ad862b7c835440`, complete `spring-core/` module fixture.
- Source ZIP SHA256: `68572527bfad750c2ab2c55dcbab1324568a4584d0d122cc3a4dfac8c139bd0c`.
- Reused graph SHA256: `7a8d957112b48ec2710afb16263211638540d5489b25dc6f313d4dd6b2afbcea`; snapshot revision: `3352a120ff0a3ffe0b24`.
- `../graph-bindings.json` retains exact paths and producer/candidate provenance. Although Java and Kotlin share source and graph records after the manifest, this catalog binds the Kotlin graph's own full bytes and revision.

Read the complete archive through its sole final `end` record and matched all footer counts. Independently checked both archive hashes and every one of the 1,166 indexed source files' raw hash and byte size against the ZIP. Read the implementation and unresolved reference records. Each exact `{source,target,path,line}` occurs as a stored `calls` edge, has both endpoint nodes, and places its physical line inside the actual source declaration. No runtime/control/index/model calls or upstream execution occurred.

## Included handoffs

Paths below are relative to `src/main/java/org/springframework/`; the JSON contains full paths and full IDs.

| Source and physical call lines | Included handoffs | Source-reviewed role |
| --- | --- | --- |
| `core/env/AbstractPropertyResolver.java:116` | `getConversionService` to `DefaultConversionService` class construction | The getter's synchronized, double-checked setup stores an independent instance at 108-121. This is distinct from the shared fallback and can affect later conversion selection. |
| `core/env/AbstractPropertyResolver.java:247,249` | `resolvePlaceholders` to `createPlaceholderHelper(true)` and `doResolvePlaceholders` | Preserves both emitted steps of lazy non-strict helper selection and replacement handoff, not just construction. |
| `core/env/AbstractPropertyResolver.java:255,257` | `resolveRequiredPlaceholders` to `createPlaceholderHelper(false)` and `doResolvePlaceholders` | Preserves the corresponding independent strict helper and replacement handoff. |
| `core/env/AbstractPropertyResolver.java:281` | `createPlaceholderHelper` to `PropertyPlaceholderHelper` class construction | Lines 280-282 pass delimiter, separator, escape and unresolved-text policy settings. |
| `util/PropertyPlaceholderHelper.java:70` | Its five-argument constructor to `PlaceholderParser` class construction | Lines 64-71 transfer the same settings into the parser. This is the task's parser boundary, not a demand to explore the full grammar. |
| `core/env/AbstractPropertyResolver.java:309` | `convertValueIfNecessary` to `DefaultConversionService.getSharedInstance` | Lines 298-312 choose this fallback only without an instance service and after the assignability fast path. It is not proof that conversion succeeds or even runs on every lookup. |

These are all emitted edges within the task's selected Java implementation methods. Excluded edges include default-escape system-property initialization, aggregate `validateRequiredProperties` failure construction, unrelated environment setup, logging/assertions, and conversion-service/parser internals beyond the rubric's explicit boundaries. Their execution or source delivery alone is not task-relationship utility.

## Unresolved Kotlin entry surface and Java gaps

All four references in `src/main/kotlin/org/springframework/core/env/PropertyResolverExtensions.kt` are explicitly `resolved=false`, reason `extension receiver dispatch unsupported`:

| Physical line | Source-reviewed delegation, not an accepted resolved edge |
| --- | --- |
| 30 | Nullable String operator `get` to `getProperty(key)` |
| 41 | Reified nullable typed extension to `getProperty(key, T::class.java)` |
| 51 | Reified default-valued extension to `getProperty(key, T::class.java, default)` |
| 61 | Reified required extension to `getRequiredProperty(key, T::class.java)` |

No fabricated extension-to-interface or extension-to-implementation tuple is in the catalog. Source can explain these exact mappings; an unresolved reference or textual mention cannot earn resolved-relationship delivery credit.

Important downstream calls are absent too:

- `PropertySourcesPropertyResolver.java:60,65,70` overload forwarding is unresolved. The ordered lookup at 80, nested processing at 84/88 and conversion return at 92 are unresolved with loop-element typing limitations. This entire file contributes zero resolved `calls` edges, despite its central semantic role.
- Default/required wrappers in `AbstractPropertyResolver.java:216,222,228,237` have unresolved inherited-candidate calls; the graph does not establish their null/exception behavior. The selected nested-policy calls at line 277 are also unresolved.
- `AbstractPropertyResolver.java:286` passes `this::getPropertyAsRawString` into helper replacement, but replacement overload resolution is unsupported. `PropertyPlaceholderHelper.java:96` parser replacement is unresolved because of the complex `this` receiver. Neither callback dispatch nor parser recursion is established by the construction edges.
- The assignability test at `AbstractPropertyResolver.java:306` and service conversion at 311 are unresolved. The accepted shared-service accessor edge must not substitute for actual conversion dispatch or retry/exception semantics.

Retained calls all have `heuristic` confidence. Constructor endpoints are class nodes, not exact overload/runtime execution proof. AST node fidelity, any known `partial=false`, and a matching snapshot hash do not make the archive semantically complete or prove current upstream freshness. A validated source-call or caller packet can establish delivery of a reviewed stored tuple only; source receipts, quote receipts, complete semantic answers and actual model usage remain separate questions. Existing operation-reuse and selection-bias disclosures remain in force.
