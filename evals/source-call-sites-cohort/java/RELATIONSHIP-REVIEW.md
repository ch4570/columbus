# Java resource navigation: reviewed stored relationships

This private, prelaunch catalog supplements `cases.json`, `criteria.json` and `SOURCE-REVIEW.md`; it does not change their 5 findings or 18 clauses. It contains **19** actual `calls` edges useful to the declared resource-routing, coordinate, lookup and relative-handle mechanism. It is not a complete semantic call graph or evidence that a model used the graph.

## Bound inputs and review method

- Upstream: Spring Framework `4c8c6409a27a62ab163d3b6196ad862b7c835440`, complete `spring-core/` module fixture, not the entire multi-module repository.
- Source ZIP SHA256: `68572527bfad750c2ab2c55dcbab1324568a4584d0d122cc3a4dfac8c139bd0c`.
- Reused graph SHA256: `b624d888e8a35f55c6f43f3255c2b21878d56e75d1e764442e9571d1fa998b23`; snapshot revision: `cf482b13ebb638a175d9`.
- Exact fixture locations, producer/candidate identities and historical timing limitations remain in `../graph-bindings.json`.

Read the complete saved archive through its sole final `end` record and checked every footer count. Independently rehashed the graph and ZIP, and matched all 1,166 indexed files' raw hashes and byte sizes to their ZIP members. Reviewed actual production source and call-reference records, not snippets synthesized from edge evidence. Every catalog tuple occurs in the archive, both endpoint IDs exist, and its physical call line lies inside its actual source node. Entries preserve exact IDs and are sorted by path, line, source and target. No repository execution, index/export, control capture or model invocation was performed.

## Inclusion boundary and physical source checks

Paths in this table are relative to `src/main/java/org/springframework/`. Full paths and exact endpoint identities are in `relationships.json`.

| Source and physical call lines | Included handoffs | Why useful to the scored mechanism |
| --- | --- | --- |
| `core/io/DefaultResourceLoader.java:158,159` | `getResource` to `getProtocolResolvers`, then `ProtocolResolver.resolve` | Connects registration-order traversal to the first-non-null override before built-in routing. The latter endpoint is the interface declaration, not a resolved runtime implementation. |
| `core/io/DefaultResourceLoader.java:166,169,172` | Default path hook; `ClassPathResource` and `ClassPathAllResource` construction | Distinguishes slash, classpath and classpath-all route selection. The last class's aggregation internals remain excluded. |
| `core/io/DefaultResourceLoader.java:177,178` | `ResourceUtils.toURL`, `ResourceUtils.isFileURL`, `FileUrlResource` and `UrlResource` construction | Preserves all four emitted routing handoffs, including all three distinct targets on line 178. The classifier at `util/ResourceUtils.java:282-285` and URL helper boundary at 413-422 were inspected; URL-connection behavior is not implied. |
| `core/io/DefaultResourceLoader.java:199` | `getResourceByPath` to `ClassPathContextResource` construction | Establishes the default classpath-context handle, not a filesystem interpretation of slash paths. |
| `core/io/ClassPathResource.java:86,112` | Both ClassLoader/Class constructors to `StringUtils.cleanPath` | Connects the two coordinate-storage branches to lexical normalization. The helper at `util/StringUtils.java:735-815` is not a traversal-security check. |
| `core/io/ClassPathResource.java:154,225` | `exists` and `getURL` to `resolveURL` | Distinguishes null-test existence from missing-URL failure and from direct stream access. |
| `core/io/ClassPathResource.java:239,240,241` | `createRelative` to `StringUtils.applyRelativePath` and the two `ClassPathResource` constructions | Preserves both context-dependent constructor branches and the directory-relative helper at `util/StringUtils.java:710-721`. |
| `core/io/DefaultResourceLoader.java:310,311` | Nested `ClassPathContextResource.createRelative` to relative-path helper and subtype construction | Covers the explicitly scored context subtype's relative-handle behavior. The source endpoint remains the nested method, not the enclosing loader class. |

This includes every emitted call in those in-scope methods, not a selected single success edge. Internal normalization/URL utility algorithms beyond the declared helper boundary, `ClassPathAllResource` aggregation, `isReadable`, equality, filename/description helpers, caches, assertions and unrelated production/test callers are not accepted utility relationships. Their presence elsewhere in the archive cannot earn task-relationship credit by itself.

## Relevant absent edges and interpretation limits

The source still requires explanation when the graph is incomplete:

- The `MalformedURLException` fallback calls `getResourceByPath` at `DefaultResourceLoader.java:182`, but that reference is unresolved because the catch scope is unsupported. The emitted line-166 edge must not be relabeled as line 182.
- Loader selection at `DefaultResourceLoader.java:107`, its `getClassLoader` calls at 169/172/199, `ClassPathResource.java:92,116` default-loader/package helpers, and the context subtype's `getPath`/`getClassLoader` calls at 305/310/311 have no resolved edges. References record receiver/inherited-candidate limitations.
- All three URL lookups at `ClassPathResource.java:176,179,182` and stream lookups at 203/206/209 remain unresolved. No accepted relationship establishes direct stream opening, closing, caching or JDK dispatch. The implementation bodies supply those semantic facts.
- Constructor delegation at `ClassPathResource.java:71` and the context subtype's `super` call at `DefaultResourceLoader.java:300` have no corresponding stored `calls` edge. The retained `new` edges target class nodes, not a proven overload or constructor execution.

All retained edge confidence values are `heuristic`, even where node syntax fidelity is AST-based. A hash-bound, fully delivered packet may demonstrate delivery of these stored tuples, but neither AST fidelity nor an index snapshot proves runtime dispatch, semantic completeness, current upstream freshness or final-answer correctness. Source-only and quote-only receipts remain distinct from reviewed graph-relationship delivery. The reused operation and graph-selection bias described in `SOURCE-REVIEW.md` remain unchanged.
