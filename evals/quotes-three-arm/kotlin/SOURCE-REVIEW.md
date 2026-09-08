# Kotlin proxy-hint registration: prospective source review

Prepared before any model launch for `kotlin-proxy-hint-registration`. This is a new operation on the previously used Spring corpus, not a held-out repository, a historical-answer revision, or a measured token-savings result. All source and tests were read only; no Spring code, tests or builds were executed. Freeze this case, criteria, review, source inventory, runtime and shared protocol before trials.

## Pin and complete module scope

The source is [Spring Framework commit 4c8c6409a27a62ab163d3b6196ad862b7c835440](https://github.com/spring-projects/spring-framework/tree/4c8c6409a27a62ab163d3b6196ad862b7c835440), with the complete `spring-core` module as the model's repository root. This is not the complete multi-module Spring Framework repository and must not be described that way.

The pre-existing local ZIP `/tmp/columbus-spring-navigation-source.zip` has SHA-256 `68572527bfad750c2ab2c55dcbab1324568a4584d0d122cc3a4dfac8c139bd0c`, is **2,174,897 compressed bytes**, and contains **1,166 files / 7,120,331 uncompressed bytes** beneath `spring-core/`. Strip that one scope prefix when materializing the model corpus. Do not construct an evidence-only fixture.

Independent checks in this review established that the local Git HEAD is the pinned commit; the pinned Git tree has exactly the same 1,166 module blob paths as the ZIP; every ZIP member's Git blob hash matches that tree; and all 1,166 extracted source files match the ZIP bytes. Existing local `.columbus` SQLite/WAL/SHM files are diagnostic cache extras, not source inventory, and must not enter the trial corpus. The sorted compact JSON `{relative_path: sha256}` inventory hash is `53bd4243666ca2f8ad02a3f00b349dd565ac10f1df889e8041bc4c1b87753143`; `source.json` retains all entries, not just reviewed files.

The module sources carry Apache-2.0 headers. The repository-root [LICENSE.txt](https://github.com/spring-projects/spring-framework/blob/4c8c6409a27a62ab163d3b6196ad862b7c835440/LICENSE.txt) has SHA-256 `56dfc19e0dc836e30177332f73e8e6fbc297941acf3d906eec6eaaa46c2c452a`. That root file is outside the historical module-only ZIP; do not claim it is one of the 1,166 module files.

## Citation and semantic contract

All six finding IDs and all 20 criteria are mandatory in each arm. Each criterion corresponds to an explicit topic in the question or finding description. Equivalent correct wording is accepted. A complete correct quoted mechanism may establish a detail not separately repeated in prose, and supporting explanation may occur in another finding; contradictory prose fails the affected criterion. A cited range without supporting text is not itself an explanation. Scope exclusions are boundaries, not extra facts an answer must recite.

Use one contiguous representative quote within a cited range of at most 40 physical lines per finding. The quote must be literal under the unchanged harness indentation convention; the cited range must contain the private marker and cover a listed call line. The following ranges are independently checked witnesses, not mandatory exact choices. The model receives finding IDs/descriptions but no private paths, markers, call lines or this review. Other helper/test facts may be explained from separate source reads; they need not fit into the representative quote. Never stitch distant excerpts or insert ellipses into an alleged verbatim quote.

| Finding | Repository-relative representative path | Range | Marker/call line |
| --- | --- | --- | --- |
| `kotlin-bridges` | `src/main/kotlin/org/springframework/aot/hint/ProxyHintsExtensions.kt` | 27–28 | 28 / 28 |
| `registration-lifecycle` | `src/main/java/org/springframework/aot/hint/ProxyHints.java` | 48–53 | 51 / 51 |
| `interface-validation` | `src/main/java/org/springframework/aot/hint/JdkProxyHint.java` | 168–177 | 170 / 176 |
| `interface-storage` | `src/main/java/org/springframework/aot/hint/JdkProxyHint.java` | 43–47 | 44 / 44 |
| `hint-state-identity` | `src/main/java/org/springframework/aot/hint/JdkProxyHint.java` | 90–101 | 95 / 95 |
| `registry-deduplication` | `src/main/java/org/springframework/aot/hint/ProxyHints.java` | 32–41 | 32 / 40 |

These ranges contain 2, 6, 10, 5, 12 and 10 physical lines respectively. The Kotlin description deliberately chooses the ProxyHints extension as representative while requiring both extension mappings in prose; it does not demand one quote spanning different Kotlin files. Likewise the registry quote represents storage/exposure, while completed-hint and TypeReference equality require helper navigation.

## Reviewed implementation

### Kotlin bridges and test interpretation

[ProxyHintsExtensions.kt 27–28](https://github.com/spring-projects/spring-framework/blob/4c8c6409a27a62ab163d3b6196ad862b7c835440/spring-core/src/main/kotlin/org/springframework/aot/hint/ProxyHintsExtensions.kt#L27-L28) maps `KClass` arguments to `.java`, constructs the typed array and spreads it to the Java Class-varargs member. [JdkProxyHintExtensions.kt 27–28](https://github.com/spring-projects/spring-framework/blob/4c8c6409a27a62ab163d3b6196ad862b7c835440/spring-core/src/main/kotlin/org/springframework/aot/hint/JdkProxyHintExtensions.kt#L27-L28) does the same on the builder receiver. The ordered mapping does not remove repetitions. The expression results are the fluent Java receiver returns, not Unit, a new registry, or a recursive call to the same Kotlin extension.

Both Kotlin extension test files at 31–37 mock the receiving Java object, stub its Class-varargs member and verify forwarding of String/Int KClasses to Java classes. They do not exercise production validation. Their example arguments must not be used as evidence that String/primitive classes are valid real proxy interfaces. Tests were read, not run.

### Java registration lifecycle

[ProxyHints.java 48–79](https://github.com/spring-projects/spring-framework/blob/4c8c6409a27a62ab163d3b6196ad862b7c835440/spring-core/src/main/java/org/springframework/aot/hint/ProxyHints.java#L48-L79) contains consumer, TypeReference-varargs and Class-varargs registration. Each varargs form supplies a consumer that calls the corresponding builder overload. The consumer form makes a new builder, invokes the callback, builds, inserts and returns the original ProxyHints instance. There is no Class-to-TypeReference hop through another ProxyHints overload.

The source performs insertion only after callback and build complete normally. Under the explicitly limited callback scope, either failure propagates without inserting a hint for that invocation; prior registry entries are untouched. This is not general transactionality over arbitrary callback side effects. A duplicate equal hint can be ignored by the set while the method still returns `this`.

### Validation versus reference-only storage

[JdkProxyHint.java 134–177](https://github.com/spring-projects/spring-framework/blob/4c8c6409a27a62ab163d3b6196ad862b7c835440/spring-core/src/main/java/org/springframework/aot/hint/JdkProxyHint.java#L134-L177) calls `toTypeReferences` before the Class-path addAll. The helper first collects names of concrete/non-interface or sealed-interface inputs and throws IllegalArgumentException when that collection is nonempty. Thus the current addition does not partially append its valid prefix before discovering an invalid class.

The valid Class sequence passes through [TypeReference.listOf at 94–96 and of(Class) at 73–75](https://github.com/spring-projects/spring-framework/blob/4c8c6409a27a62ab163d3b6196ad862b7c835440/spring-core/src/main/java/org/springframework/aot/hint/TypeReference.java#L73-L96), then ReflectionTypeReference.of at 45–49. Mapping preserves encounter order and multiplicity. The input assumptions deliberately avoid requiring a separate taxonomy of null Class values, local/anonymous canonical names or invalid names.

The TypeReference builder overload at JdkProxyHint.java 124–127 simply appends `Arrays.asList`. It does not validate interface-ness, sealing or class availability. TypeReference.of(String) delegates to SimpleTypeReference.of; the latter parses names without loading the described class. The question assumes well-formed names, so detailed syntax validation is not required. ProxyHintsTests 39–63 corroborates Class validation and name-backed references to a class unavailable in this module.

### Accumulation, empty lists and the scoped null misuse

Builder state is an initially empty LinkedList at JdkProxyHint.java 109–117. Both addition methods at 124–137 append rather than replace, retaining repeated elements and call order. Empty typed arrays do nothing. No registration/build minimum-count guard exists, so an untouched builder can produce an empty-interface hint; actual proxy creation is not being tested or promised.

The constructor at 43–47 copies the list with List.copyOf and copies metadata fields. The getter at 72–74 returns the resulting unmodifiable list. Later builder additions cannot change that list snapshot; this is not a deep-copy guarantee for arbitrary custom reference objects, which are excluded.

The question expressly includes one Java misuse despite the package's `@NullMarked` non-null API contract (`package-info.java` 5–8): a non-null TypeReference array containing null. Arrays.asList and LinkedList.addAll admit the element, while List.copyOf rejects it with NullPointerException during completed-hint construction, before registry insertion. No Kotlin nullability bypass, null array or null Class/KClass analysis is required. This conclusion uses ordinary JDK collection contracts and the visible call order, not an executed test.

### Metadata, equality and hash collisions

JdkProxyHint.Builder fields at 111–113 default to null reachability and false serialization; setters at 144–158 overwrite their respective fields and return the builder. Construction at 43–47 snapshots those current fields, with getters at 76–88. Null reachability is the no-condition state documented by ConditionalHint.getReachableType at 32–37; conditionMatches and its classloader helper are explicitly outside scope.

[JdkProxyHint.equals/hashCode at 90–101](https://github.com/spring-projects/spring-framework/blob/4c8c6409a27a62ab163d3b6196ad862b7c835440/spring-core/src/main/java/org/springframework/aot/hint/JdkProxyHint.java#L90-L101) uses ordered-list equality plus nullable reachability and serialization equality. The hash uses only the interface list. Distinct metadata can therefore collide in hash without being equal. Do not score an answer as correct if it claims hashing alone causes set deduplication. JdkProxyHintTests 41–71 corroborates cross-representation equality, condition differences and order sensitivity; serialization equality follows the production method even though those tests do not separately exercise every combination.

### Whole-hint deduplication and type identity

[ProxyHints.java 32–51](https://github.com/spring-projects/spring-framework/blob/4c8c6409a27a62ab163d3b6196ad862b7c835440/spring-core/src/main/java/org/springframework/aot/hint/ProxyHints.java#L32-L51) uses a LinkedHashSet and streams it directly. Equal completed hints are suppressed without moving/replacing the first equal entry, and unique entries retain insertion order. No sorting or union-merging of interface lists occurs.

ReflectionTypeReference and SimpleTypeReference extend AbstractTypeReference. Its [equals/hashCode at 85–94](https://github.com/spring-projects/spring-framework/blob/4c8c6409a27a62ab163d3b6196ad862b7c835440/spring-core/src/main/java/org/springframework/aot/hint/AbstractTypeReference.java#L85-L94) use case-sensitive canonical names, unlike its separate compareTo method. Correctly named references for the same type can therefore compare equal across Class-backed and name-backed representations. ProxyHintsTests 76–81 directly corroborates suppression of such a repeated registration. That deduplication is at whole-hint level; duplicate elements within one interface list remain present and affect list equality.

## Reviewed file hashes

All paths are relative to the complete spring-core root. Every listed file was independently matched to the ZIP and pinned Git blob. Source.json also retains their SHA-256 values and the full corpus inventory.

| File suffix under `src/` | Physical lines | SHA-256 |
| --- | ---: | --- |
| `main/kotlin/org/springframework/aot/hint/ProxyHintsExtensions.kt` | 28 | `557763f3ff7e8672386410b99031af4d5831bbe0ed6076ffe8218ddc7e9ac506` |
| `main/kotlin/org/springframework/aot/hint/JdkProxyHintExtensions.kt` | 28 | `1fe4ece8a2e848b39b50a7f6506b7a1093535b3697c3026fbeeb9a2394f9d62c` |
| `main/java/org/springframework/aot/hint/ProxyHints.java` | 81 | `159e9d3d3324a775bd1d2ea8c55f34f2a1406458eb6d3e7c097af8e158272412` |
| `main/java/org/springframework/aot/hint/JdkProxyHint.java` | 180 | `7475347331e29f4340b192d044bd4d144f6a1901c59d343330cc5d48004ed502` |
| `main/java/org/springframework/aot/hint/TypeReference.java` | 98 | `706f34ea6ad5b01407c80415ec48c82799c1a245f00dcc0f2e48ee0c7a8aa6df` |
| `main/java/org/springframework/aot/hint/AbstractTypeReference.java` | 101 | `3fa19e601701d3d6e116049c87e27eb30d8b2c23b56f5bf98979cf70d52a2da1` |
| `main/java/org/springframework/aot/hint/ReflectionTypeReference.java` | 62 | `52fd56e6e1c122394540e73fa4e7bcd0de704246d22faa6095a7773359e0d4f6` |
| `main/java/org/springframework/aot/hint/SimpleTypeReference.java` | 109 | `7afa854cd0c2d64016c43991ebd42cdcd69bb90de8348532c1c1fa5afd68dcc6` |
| `main/java/org/springframework/aot/hint/ConditionalHint.java` | 56 | `dfbac749bacec30ec6314779fb9d440898c1f08773c9eed4d28f195d0bf103ea` |
| `main/java/org/springframework/aot/hint/package-info.java` | 8 | `42de4d16604beda800eb2a320062f378cb06555e5745f6661f3650eaae1d7bcb` |
| `test/kotlin/org/springframework/aot/hint/ProxyHintsExtensionsTests.kt` | 40 | `584e76323e49fbe64c1c517f112a781de9105e2d34b432c8c5946ad85eeed325` |
| `test/kotlin/org/springframework/aot/hint/JdkProxyHintExtensionsTests.kt` | 40 | `0dab53da2abbb8c6bfea738db10a3b398495a3a96edcee449fecdda7b979b251` |
| `test/java/org/springframework/aot/hint/ProxyHintsTests.java` | 126 | `037f4226aeda5376859b890254f9ff0d99493c27c29edb7ce87354df6980f5e3` |
| `test/java/org/springframework/aot/hint/JdkProxyHintTests.java` | 81 | `3f1f1e3a4306dbfc8c6f06d3a7d39c1c165db340e42a5e8f75e8ffe5c05965d1` |

## Useful relationship controls, not inferred dispatch

An existing source-matching saved archive was inspected read-only: `/tmp/columbus-token-kotlin-batch/graph.jsonl.xz`, SHA-256 `d61661f62e09e0750ab1b174179c6f7f1ac62b9295b2323965db0e66e2cbba7a`, recorded revision `c3eb9cdaa72e23456cca`. This is evidence of actual saved relationships, not a promise about the final cohort graph. Recheck exact rows against that cohort's frozen graph before accepting controls.

Two useful production `calls` edges were present and agree with literal source:

1. Path `src/main/java/org/springframework/aot/hint/ProxyHints.java`, line **51**. Source ID `src/main/java/org/springframework/aot/hint/ProxyHints.java::org.springframework.aot.hint.ProxyHints.registerJdkProxy:method(Consumer<JdkProxyHint.Builder>)`; target ID `src/main/java/org/springframework/aot/hint/JdkProxyHint.java::org.springframework.aot.hint.JdkProxyHint.Builder.build:method()`. Literal call: `builder.build()`.
2. Path `src/main/java/org/springframework/aot/hint/JdkProxyHint.java`, line **135**. Source ID `src/main/java/org/springframework/aot/hint/JdkProxyHint.java::org.springframework.aot.hint.JdkProxyHint.Builder.proxiedInterfaces:method(Class<?>...)`; target ID `src/main/java/org/springframework/aot/hint/JdkProxyHint.java::org.springframework.aot.hint.JdkProxyHint.Builder.toTypeReferences:method(Class<?>...)`. Literal call: `toTypeReferences(proxiedInterfaces)`.

Both rows are marked `confidence: heuristic` in that archive; they are navigation evidence, not compiler/runtime proofs. Both Kotlin extension declarations are present with distinct receivers, but this inspected graph has no outgoing call edge from either Kotlin bridge. Do not fabricate cross-language edges or require them as the only way to demonstrate useful graph navigation. The semantic oracle is the pinned source, not graph completeness. Source/search/quote delivery alone must not be credited as relationship use by the new relationship recognizer.

The exact Kotlin declaration IDs are `src/main/kotlin/org/springframework/aot/hint/ProxyHintsExtensions.kt::org.springframework.aot.hint.registerJdkProxy:function(KClass<*>)@ProxyHints` and `src/main/kotlin/org/springframework/aot/hint/JdkProxyHintExtensions.kt::org.springframework.aot.hint.proxiedInterfaces:function(KClass<*>)@JdkProxyHint.Builder`. They are discovery/source targets, not substitute relationship receipts.

### Final prelaunch relationship inventory

The newly prepared cohort graph confirms both reviewed method calls. `relationships.json` also includes the directly inspected fresh-builder construction at ProxyHints.java:49 and completed-hint construction at JdkProxyHint.java:165. The stored constructor-call targets are the corresponding class nodes, not fabricated constructor-method IDs. These four `calls` relationships are within the specified registration/build/validation lifecycle. The recognizer must match their exact source/target/path/line and source hashes; later controls exercise both runtime variants. No model had run when these were selected. Source-only delivery, contains edges and the omitted Kotlin bridge calls do not replace them.
