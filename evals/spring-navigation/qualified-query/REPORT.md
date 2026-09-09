# Package-omitted method lookup

A current saved Spring snapshot exposed a navigation defect: `explore DefaultResourceLoader.getResource` treated the query as loose FTS words and began with nested ClassPathAllResource.getDescription. Class-only snippets and signatures also exhausted their 6,000-byte budget before including getResource. The fully qualified method query already worked.

Search now prioritizes component-boundary qualified-name suffix matches for dotted identifiers, after full exact matches and before lexical matches. It retains multiple package candidates, respects path/language filters, and labels suffix evidence separately from exact-name evidence. It does not create semantic call edges or choose one ambiguous declaration. No schema or graph mutation is needed.

On the same saved snapshot, the short query now places the complete getResource source at lines 154–185 first, matching the full-name route. Response bytes are 5,788 versus 5,964 before; the significant change is the relevant first body, not the small payload difference. The packet remains globally truncated and semantically incomplete. Raw class/short/full-name responses are retained here.

Both parser engine suites pass 210 tests, including package ambiguity, identifier boundaries, path filtering and full-name precedence. Root tests pass 53 and skill validation passes. The skill now documents the direct Class.method route and class-only budget limitation. These are deterministic navigation checks, not a repeat of the failed model pair or proof of actual token savings.
