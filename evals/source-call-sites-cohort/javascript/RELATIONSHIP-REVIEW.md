# JavaScript URI composition: reviewed stored relationships

This private, prelaunch catalog supplements the unchanged 5 findings and 19 clauses in `cases.json`, `criteria.json` and `SOURCE-REVIEW.md`. It includes **22** source-reviewed actual `calls` edges across URI entry points, merge/copy behavior, base-path selection and default parameter traversal. It is neither a complete call graph nor a claim of model adoption or token savings.

## Bound inputs and review method

- Upstream Axios pin: `e5a33366d75b65f88052b230b103731eb7dcb793`, complete 242-file superproject source ZIP.
- Source ZIP SHA256: `c53e20043fc22e23f2b8a47d12a68dac007a71c3f9ae652d3188ceb4ba2b2345`.
- Reused graph SHA256: `9bdd1b2ca6ff306b3700d141bdeab1593f511e73046deaa89ff27c7b9e4b17c7`; snapshot revision: `14898a983357327f60a7`.
- Exact fixture paths, source inventory and producer/candidate compatibility are retained in `../graph-bindings.json`; this is not a fresh export or new indexing-cost measurement.

Independently checked graph/ZIP hashes, read through the sole final archive `end` record, and matched every footer count. Rehashed all 237 indexed files and checked their byte sizes against ZIP source members. The complete ZIP also retains five unindexed files already disclosed in the binding: `.gitignore`, oversized `package-lock.json`, `test/unit/adapters/axios.png`, `cert.pem` and `key.pem` in that test directory. Graph absence does not mean these source files were removed. Source review used actual implementation bytes and reference records, not edge-evidence snippets. Every catalog tuple is an actual edge with existing endpoints and a physical call line within its source node. No JavaScript, tests, runtime/control/index commands or models were run.

## Inclusion boundary and exact source checks

| Source and physical call lines | Included handoffs | Why useful to the scored mechanism |
| --- | --- | --- |
| `lib/core/Axios.js:201,202,203` | `Axios.getUri` to `mergeConfig`, `buildFullPath`, `buildURL` | All three synchronous composition handoffs; no `_request`, interceptor, dispatch or adapter path is credited. Imports bind these helpers to separate files. |
| `lib/core/buildFullPath.js:17,19` | `isAbsoluteURL`, `combineURLs` | Connects the relative/absolute classifier and conditional string combination. Both short target bodies were checked against the pin. |
| `lib/core/mergeConfig.js:36,38` | `mergeDeepProperties` to `getMergedValue` for override and fallback | Covers default merge policy for `params` and `allowAbsoluteUrls`, including defined-versus-undefined handling. |
| `lib/core/mergeConfig.js:45,52,54` | `valueFromConfig2` and both `defaultToConfig2` branches to `getMergedValue` | Covers per-call-only URL versus default-selecting base URL/serializer, with copy/merge behavior at the common helper. |
| `lib/utils.js:348,350` | `merge.assignValue` to `isPlainObject` | The plain-object classification directly chooses the scored recursive merge/copy branches; these are not unrelated utility calls. The two textual tests on line 348 are represented by the archive's one stored tuple, not invented duplicates. |
| `lib/utils.js:349,351,360` | Recursive merge into an existing result, recursive fresh-object copy, and `forEach` traversal of each merge input | Connects fresh recursive plain-object construction and ordered assignment; array slicing/non-plain sharing still require source inspection at 352-355. |
| `lib/helpers/toFormData.js:158,175` | `defaultVisitor` to `isFlatArray` and `isVisitable` | Chooses repeated flat-array values versus nested recursive visits in the default supported data path. |
| `lib/helpers/toFormData.js:168,179` | Flat-array element conversion; ordinary value conversion and `renderKey` | Preserves both same-line targets at 179. Helpers at 39-45 and 116-125 establish nested bracket keys, Date ISO text and boolean strings; array null/undefined exclusion is visible at 164-171. |
| `lib/helpers/toFormData.js:207,218` | Initial build and recursive build from the visitor-result callback | Connects the default walk after object-member null/undefined filtering at 201-204. The nested callback's exact source ID is retained instead of attributing its call to the outer function. |

The list includes every actual emitted handoff within these task-relevant branches, not one convenient entry edge. The boundary deliberately excludes:

- `_request` and HTTP-method aliases, headers and `validateStatus` merge policies, and unrelated network paths.
- `toFormData` line 167's `renderKey` call, which is conditional on `indexes === true`; the task fixes default `indexes=false`. Its presence on the same line as the rubric marker does not make it a useful executed-default-path handoff.
- `removeBrackets` calls at 43/162: for the explicitly scoped keys without special `[]` suffixes they are identity normalization, not the scored bracket construction. The relevant `renderKey` handoff at 179 remains included. Special key suffix modes cannot become hidden utility requirements.
- Caseless `findKey` and context-detection utilities at `lib/utils.js:347,344`, full type-predicate internals, assertions/logging, binary/file handling, custom visitor modes and parser/adapter behavior outside this operation.

## Relevant absent edges and interpretation limits

Actual source supplies important handoffs that this heuristic graph does not resolve:

- `mergeConfig.js:24,26` calls through `utils.merge.call`/`utils.merge`, the iteration at 99 and policy-variable dispatch at 101 are unresolved. The accepted downstream `lib/utils.js` tuples do not manufacture a stored cross-file merge link.
- `buildURL.js:50` selected custom serializer, native `params.toString()` at 53 and Axios accumulator construction/`.toString(_encode)` at 54 are unresolved. There are no resolved calls from `buildURL` in this saved graph. Its source still determines short-circuiting, encoder choice, fragment removal and delimiter behavior.
- `AxiosURLSearchParams.js:39` calls `toFormData`, but the reference is unresolved; the append and encoder/pair-map calls at 45/50/53-55 are unresolved too. There are no resolved `calls` edges from this file. Neither a source quote nor an import creates the missing accumulator relationship.
- `toFormData.js:56` passes `isVisitable` as an array callback; `visitor.call` at 202 and receiver `formData.append` calls at 165/179 are not accepted resolved edges. Date/boolean conversion calls, native encoding/string operations and array copying also rely on source semantics rather than graph completeness.

All retained edges have `heuristic` confidence; JavaScript nodes in this archive omit `partial`, which means unknown, not `false`. A complete, hash-verified source-call page can report all stored edges for its line union without being semantically complete. It must retain actual nested source IDs and cannot promote missing or unresolved references into targets. Validated delivery of these reviewed tuples is distinct from source delivery, ready-quote delivery, final-answer correctness, runtime execution and current upstream freshness. The reused-corpus and mechanism-selection bias in `SOURCE-REVIEW.md` remains explicit.
