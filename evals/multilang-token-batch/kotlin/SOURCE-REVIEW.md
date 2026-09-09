# Predeclared source-reviewed JVM tasks

Prepared and source-reviewed before any model execution. This catalog, semantic oracle, harness, schema, runtime/skill and complete source corpus must be frozen before execution. Prior Requests criteria and results remain unchanged.

Source: Spring commit `4c8c6409a27a62ab163d3b6196ad862b7c835440`; 1,166 files / 7,120,331 bytes. Every local file matches the existing source ZIP SHA-256 `68572527bfad750c2ab2c55dcbab1324568a4584d0d122cc3a4dfac8c139bd0c`.

Both tasks are new questions on the same previously inspected Spring repository. They are not held-out repositories or two independent repository samples. Source review and existing test source supply the oracle; no target tests, project build, JVM runtime behavior or model execution was performed here.

Acceptance remains 100% of the requested finding IDs, every unchanged citation rule, and every must-state semantic condition for both arms. Unexpected/duplicate findings and contradictions fail. One bounded contiguous verbatim quote per finding is sufficient; all listed semantics must be established by correct prose or an actual supporting source quote, including when support is in another reviewed range; a broad line range without its supporting quote does not establish a missing explanation. Do not stitch excerpts or expand the 40-line citation bound. Private oracle/declarations/source metadata must not be inserted into the model prompt or source corpus. Positive behavior clauses are required facts. Clauses phrased as prohibitions constrain contradictions; a model need not recite an unrelated warning to pass. Scope exclusions and evidence limitations are grading boundaries, not additional facts the answer must repeat.

The compiler/parser graph is not the answer oracle. declarations.json contains current searchable declaration IDs as preparation evidence only; missing call edges do not excuse a missing behavioral requirement.

## java-property-resolution

Trace how PropertySourcesPropertyResolver resolves ordinary, typed, default-valued and required property lookups across multiple sources. Explain which value wins, nested-placeholder versus raw retrieval, strict and non-strict placeholder behavior, conversion-service selection (including explicit configuration and getConversionService()), and what happens when processing returns null or throws. Include whether later sources or defaults are tried after a failure and whether values are cached. Follow the implementation in this checkout. Stay at these API boundaries: do not enumerate all converters or the full placeholder escape/default grammar, and do not include validateRequiredProperties. Do not execute the project or assume custom PropertySource/conversion implementations always succeed.

### source-selection

Required citation marker: `Object value = propertySource.getProperty(key);` in `src/main/java/org/springframework/core/env/PropertySourcesPropertyResolver.java`, line 80.

- Lookup traverses the supplied PropertySources in its iteration order; do not invent a universal environment/source priority order.
- A null PropertySources collection or no non-null source value returns null. Null results from individual sources are skipped.
- The first non-null raw value is processed and its converted result returned immediately. A conversion returning null still ends this search; later sources are not tried.
- Placeholder/conversion exceptions propagate; there is no catch-and-fallback to a lower-priority source. The lookup does not cache resolved property values, so later calls query the current sources again.

Reviewed support: `src/main/java/org/springframework/core/env/PropertySourcesPropertyResolver.java` 73–100.

### nested-value-processing

Required citation marker: `value = resolveNestedPlaceholders(string);` in `src/main/java/org/springframework/core/env/PropertySourcesPropertyResolver.java`, line 84.

- Ordinary String and typed getProperty overloads pass resolveNestedPlaceholders=true; getPropertyAsRawString passes false and requests String conversion.
- With resolution enabled, any String value is resolved before conversion. A non-String CharSequence is converted to a string and resolved only when the requested target is String or CharSequence; do not apply that branch to every target type or every object.
- When resolution is disabled or no eligible string-like branch applies, the raw value goes straight to later conversion. The sequence is source selection, eligible nested resolution, then conversion.
- Placeholder helper lookup uses this::getPropertyAsRawString. Raw means nested-placeholder expansion is disabled here; it does not mean type conversion is disabled.

Reviewed support: `src/main/java/org/springframework/core/env/PropertySourcesPropertyResolver.java` 58–100; `src/main/java/org/springframework/core/env/AbstractPropertyResolver.java` 280–287.

### placeholder-policy

Required citation marker: `resolvePlaceholders(value) : resolveRequiredPlaceholders(value)` in `src/main/java/org/springframework/core/env/AbstractPropertyResolver.java`, line 277.

- ignoreUnresolvableNestedPlaceholders initially equals false. Empty nested values return unchanged; otherwise false selects resolveRequiredPlaceholders and true selects resolvePlaceholders.
- Explicit resolvePlaceholders and resolveRequiredPlaceholders choose their own non-strict/strict helpers regardless of the nested flag. Helpers are created lazily with ignore=true/false respectively; these are not cached property results.
- An unresolved placeholder is retained in placeholder form under the non-strict policy; strict resolution throws PlaceholderResolutionException, an IllegalArgumentException subtype. Do not confuse this with getRequiredProperty absence, which throws IllegalStateException.
- Ignoring unresolvable placeholders is not a promise to suppress every error: circular placeholder references still throw. No placeholder or conversion exceptions are swallowed by the resolver lookup.
- Detailed escape/default-expression grammar is outside the task; do not substitute an imagined complete placeholder algorithm for these reviewed boundaries.

Reviewed support: `src/main/java/org/springframework/core/env/AbstractPropertyResolver.java` 90–102; `src/main/java/org/springframework/core/env/AbstractPropertyResolver.java` 172–184; `src/main/java/org/springframework/core/env/AbstractPropertyResolver.java` 244–287; `src/main/java/org/springframework/util/PlaceholderParser.java` 341–365; `src/main/java/org/springframework/util/PlaceholderResolutionException.java` 30–36.

### conversion-policy

Required citation marker: `return conversionServiceToUse.convert(value, targetType);` in `src/main/java/org/springframework/core/env/AbstractPropertyResolver.java`, line 311.

- A null requested target type returns the value directly.
- If a conversion service is already configured, its convert method is used. The assignable-value shortcut is only in the no-configured-service branch; do not claim custom conversion is always bypassed for assignable values.
- With no configured service, an assignable value is returned directly; otherwise DefaultConversionService.getSharedInstance() supplies conversion. This fallback does not store that shared instance into the resolver field.
- getConversionService() instead initializes and stores a separate DefaultConversionService with synchronization/rechecking; subsequent property conversions see that configured service. setConversionService rejects null with IllegalArgumentException and replaces the field for non-null input.
- Conversion output, including null, is returned as-is. Conversion failures propagate rather than being translated into missing-property fallback or trying another source. Do not promise that every target conversion succeeds.

Reviewed support: `src/main/java/org/springframework/core/env/AbstractPropertyResolver.java` 107–128; `src/main/java/org/springframework/core/env/AbstractPropertyResolver.java` 297–312; `src/main/java/org/springframework/util/Assert.java` 173–184.

### missing-default-required

Required citation marker: `throw new IllegalStateException("Required key` in `src/main/java/org/springframework/core/env/AbstractPropertyResolver.java`, line 230.

- Ordinary nullable retrieval returns its lookup/conversion result. String and typed default overloads return the default only when that result is null; an empty string is not absence.
- Both required overloads perform lookup and throw IllegalStateException with the missing key when the result is null; otherwise they return the value.
- Because conversion may return null, a default or required-missing outcome can occur even after a non-null raw source value was found. This does not restart source iteration.
- Placeholder and conversion exceptions occur during delegated lookup and propagate through default/required overloads; these overloads do not catch them and substitute a default. The separate validateRequiredProperties aggregation API is outside this task.

Reviewed support: `src/main/java/org/springframework/core/env/AbstractPropertyResolver.java` 214–242; `src/main/java/org/springframework/core/env/PropertySourcesPropertyResolver.java` 73–100.

## kotlin-reflection-hint-state

Starting at the Kotlin ReflectionHints extensions, trace getTypeHint<T>(), registerType<T>(member categories), and registerType<T> { builder customization } through the Java implementation. Explain repeated registration for the same type, how categories combine, what an earlier returned TypeHint observes after later registration, and what remains if a customizer throws. Compare registration and lookup for an absent valid type and for a Java Class with no canonical name, and identify null-Class validation. Assume non-null category arrays/elements and callbacks. Restrict the state question to member categories; do not enumerate field/method/constructor registration or claim that recording hints executes reflection or proves native-image/runtime reachability. Do not execute the project.

### kotlin-delegation

Required citation marker: `registerType(T::class.java, typeHint::invoke)` in `src/main/kotlin/org/springframework/aot/hint/ReflectionHintsExtensions.kt`, line 37.

- getTypeHint<T>() passes the reified T::class.java to Java getTypeHint(Class<?>). It is a lookup, not automatic registration.
- The callback registration extension passes T::class.java and typeHint::invoke to the Java Class/Consumer overload. The Kotlin callback is noinline; it is adapted and passed through rather than invoked before Java registration.
- The category overload passes T::class.java and spreads *memberCategories to the Java Class/varargs overload. It does not package all categories as one category or invoke the callback overload with the caller callback.
- Registration delegates return the same ReflectionHints instance on normal completion. These extensions add syntax convenience; they do not prove runtime reflective reachability or execute reflected members.

Reviewed support: `src/main/kotlin/org/springframework/aot/hint/ReflectionHintsExtensions.kt` 26–47; `src/main/java/org/springframework/aot/hint/ReflectionHints.java` 76–143.

### registration-class-guards

Required citation marker: `if (type.getCanonicalName() != null)` in `src/main/java/org/springframework/aot/hint/ReflectionHints.java`, line 124.

- Both Class-based registerType overloads reject a null Class with IllegalArgumentException via Assert.notNull.
- A non-null Class with no canonical name is skipped: no TypeReference is created, no builder is registered and the consumer is not invoked; normal return is still this.
- A Class with a canonical name is converted through TypeReference.of and delegated to its TypeReference overload. Do not generalize the skip policy to the lookup path or claim every class always registers.
- No concurrency, type-loading or native-image execution guarantee follows from these guards.

Reviewed support: `src/main/java/org/springframework/aot/hint/ReflectionHints.java` 122–143; `src/main/java/org/springframework/util/Assert.java` 173–184.

### registration-state-errors

Required citation marker: `typeHint.accept(builder);` in `src/main/java/org/springframework/aot/hint/ReflectionHints.java`, line 100.

- The TypeReference registration path uses computeIfAbsent to keep one builder per type key and then invokes the consumer on that builder for every registration; repeated calls do not replace the builder.
- The category path creates a consumer using TypeHint.builtWith, which calls Builder.withMembers. withMembers adds to a HashSet, so categories accumulate and duplicate categories collapse rather than replacing prior categories or promising insertion order.
- Callbacks run synchronously after the builder has been obtained/stored. Callback exceptions propagate; there is no rollback or removal. A newly stored builder and any mutations made before throwing can remain observable. Do not claim transactional registration or that every thrown callback necessarily changed a category.
- The task assumes non-null category arrays/elements and a non-null callback; hostile null misuse of those arguments and constructor/method/field metadata registration are outside scope.

Reviewed support: `src/main/java/org/springframework/aot/hint/ReflectionHints.java` 98–113; `src/main/java/org/springframework/aot/hint/TypeHint.java` 140–148; `src/main/java/org/springframework/aot/hint/TypeHint.java` 154–172; `src/main/java/org/springframework/aot/hint/TypeHint.java` 267–275.

### lookup-absence-errors

Required citation marker: `return (typeHintBuilder != null ? typeHintBuilder.build() : null);` in `src/main/java/org/springframework/aot/hint/ReflectionHints.java`, line 78.

- The class lookup first calls TypeReference.of(Class), then performs a map lookup. An absent valid type yields null and does not create/register a builder.
- TypeReference.of(Class) delegates to ReflectionTypeReference.of, which rejects a null Class or null canonical name with IllegalArgumentException. Lookup does not share class-registration’s silent skip for a noncanonical class.
- If a builder exists, the result is built from its current state. A missing stored hint is not evidence that the class cannot load or that reflection is forbidden at runtime.

Reviewed support: `src/main/java/org/springframework/aot/hint/ReflectionHints.java` 76–88; `src/main/java/org/springframework/aot/hint/TypeReference.java` 67–75; `src/main/java/org/springframework/aot/hint/ReflectionTypeReference.java` 45–49; `src/main/java/org/springframework/util/Assert.java` 173–184.

### category-snapshots

Required citation marker: `this.memberCategories = Set.copyOf(builder.memberCategories);` in `src/main/java/org/springframework/aot/hint/TypeHint.java`, line 62.

- Builder.build constructs a new TypeHint, and its constructor copies the builder category set with Set.copyOf. A returned category set is an immutable snapshot, not the live mutable builder HashSet.
- After more categories are registered for the same builder, a later getTypeHint builds a new result with current accumulated categories; an earlier TypeHint/category set is not retroactively updated.
- getMemberCategories returns that copied set. This is a category-snapshot statement, not a guarantee that arbitrary callback-owned objects are deeply copied or that registrations are thread-safe.
- Do not claim that merely creating or reading hints performs reflective operations or proves runtime dispatch.

Reviewed support: `src/main/java/org/springframework/aot/hint/ReflectionHints.java` 76–79; `src/main/java/org/springframework/aot/hint/TypeHint.java` 59–67; `src/main/java/org/springframework/aot/hint/TypeHint.java` 118–124; `src/main/java/org/springframework/aot/hint/TypeHint.java` 267–294.

## Complete corpus and dependencies

Use `/tmp/columbus-spring-navigation-source.zip` for both tasks. Keep all 1,166 paths/hashes in source.json; do not construct an evidence-only fixture. The listed reviewed files define rubric support, not the file inventory available to the model.

Corroborating tests were read but not executed:
- `src/test/java/org/springframework/core/env/PropertySourcesPropertyResolverTests.java`
- `src/test/java/org/springframework/aot/hint/ReflectionHintsTests.java`
- `src/test/java/org/springframework/aot/hint/TypeHintTests.java`
- `src/test/kotlin/org/springframework/aot/hint/ReflectionHintsExtensionsTests.kt`

JDK library semantics used narrowly in the review include Map.computeIfAbsent, HashSet accumulation and Set.copyOf. JVM dependencies/build tooling are not a complete executable Spring environment. The task does not claim compiler or runtime proof, external/custom resolver success, complete placeholder grammar, or native-image reachability.
