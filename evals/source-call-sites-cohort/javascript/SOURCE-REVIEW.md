# Axios URI composition: prospective source rubric

This is a newly specified operation within a reused development repository, not a held-out repository or a broad novelty claim. No models, upstream JavaScript, test suites or builds were run while preparing it. All 5 findings and 19 zero-based criterion clauses in `criteria.json` are mandatory. Shared evidence elsewhere in the same answer, including complete quoted code, can support a clause; contradictory prose fails it. Each finding requires a cited range of at most 40 physical lines containing its private marker. The representative quote may be a contiguous subrange within that citation; matching ignores indentation only, with no stitching, and does not separately require the quote itself to contain the marker. Cross-file explanations belong in prose, not stitched quotations. Paths, ranges, marker strings and this review remain private grading data.

## Source identity and scope

The entire 242-file pinned Axios superproject archive is retained as the source scope, including implementation, tests and license. No convenient-file subset or generated installed-dependency directory replaces it. ZIP SHA256: `c53e20043fc22e23f2b8a47d12a68dac007a71c3f9ae652d3188ceb4ba2b2345`; ZIP bytes: 746720; complete source bytes: 2650116. Every ZIP member and every local snapshot file was rehashed and matched; the canonical inventory SHA256 is `2fb9ed6b024ca3d98524260d42099c1579f4986faadebb81ab7915e84946c516`.

Upstream pin: [Axios e5a33366d75b65f88052b230b103731eb7dcb793](https://github.com/axios/axios/tree/e5a33366d75b65f88052b230b103731eb7dcb793). The [official commit ZIP URL](https://codeload.github.com/axios/axios/zip/e5a33366d75b65f88052b230b103731eb7dcb793) and its requested/resolved retrieval identity come from existing `evals/overload-token-cohort/javascript/source.json`; this review reuses those bytes and does not claim a new download. `../sources.json` records full paths, prefix, inventory encoding and limits. MIT `LICENSE` is in the fixture, SHA256 `82761059eaedacb3356803aea8a170d8298609f91b14fc32ee1bfb40d690183c`. Historical provenance records no omitted gitlinks; this is not a recursive dependency checkout.

| Production path | Bytes / physical lines | Raw SHA256 |
| --- | --- | --- |
| `lib/core/Axios.js` | 6836 / 240 | `c00e716e4d26694a09e010b9837524a5d661659e6eaad2cbaa5b4304f6ab1a39` |
| `lib/core/mergeConfig.js` | 3404 / 106 | `8dc5bb930f2f5e3dcfd6ab27438ebd9ff42afb899f9929a7ac2a36dba8640cfa` |
| `lib/core/buildFullPath.js` | 783 / 22 | `44b19502ea4f5658255f13d63d45dddad1f26ea5ffd55c9c28f76da7a031cd8e` |
| `lib/helpers/buildURL.js` | 1605 / 67 | `a441ec9bf90dce12c382a422bac8ff22acba0fbae13e03e03556c1c26e359af5` |
| `lib/helpers/isAbsoluteURL.js` | 561 / 15 | `5cd00bb88f60bb9bcc44f598e13162fcac029b720308fdc1d9efb8470904cf7d` |
| `lib/helpers/combineURLs.js` | 382 / 15 | `4ba8cf99c8ecafb3eb840c80acaed436d692e3f2449f2f06a91bf1a16c3d6292` |
| `lib/helpers/AxiosURLSearchParams.js` | 1439 / 58 | `0e19b07d96a717eb1b07630c9f984be4014edf05c84f4d95ee6077f072ceb3ff` |
| `lib/helpers/toFormData.js` | 6116 / 223 | `366713d86b94d8837704ae9a6a5ef30280a9e58d81b7641b85d6b014c3b46326` |
| `lib/utils.js` | 19214 / 782 | `b21b7010034f4b47a30e840df9deaa4067b9f0066c648bc04116f30266369850` |

## Clause-to-source review

`uri_handoffs`, representative `lib/core/Axios.js:200–204` (5 lines; marker at 202):

- [0] Lines 201–203 implement the precise defaults/per-call merge, full-path construction and query-builder handoffs. Imports at the beginning of the file bind the helpers to their separate implementation files.
- [1] The method directly returns the helper result, with no catch or asynchronous wrapper in this path.
- [2] This complete method does not enter `_request`, interceptors, adapters or dispatch. That is a local URI-computation fact, not a prediction of a later actual request or a dependency callback's arbitrary side effects.

`uri_config_merge`, representative `lib/core/mergeConfig.js:43–75` (33 lines; marker at 68):

- [0] Lines 17–30,99–105 create a new result and clone/merge plain values and arrays. `lib/utils.js:343–361` recursively builds fresh plain objects and slices arrays. Non-plain values/functions can pass through; no universal deep-clone claim is justified.
- [1] Lines 43–55,67–74 distinguish per-call-only `url` from default-selecting `baseURL` and `paramsSerializer`. The helpers test undefined, not truthiness: null overrides. A missing defaults URL fallback is observable even though the ordinary task uses a supplied per-call string URL.
- [2] The complete map at 67–97 has no `params` or `allowAbsoluteUrls` entry, so 99–102 chooses `mergeDeepProperties` from 34–39. Scoped boolean values are ordinary defined-value overrides; null and undefined have different outcomes.
- [3] `getMergedValue` at 22–30 and `utils.merge` at 343–361 establish recursive plain-object merging, later precedence and array slice/replacement, not concatenation or a shallow-only spread.

`uri_base_path`, representative `lib/core/buildFullPath.js:16–22` (7 lines; marker at 18):

- [0] Line 17 calls `isAbsoluteURL`; `lib/helpers/isAbsoluteURL.js:10–14` recognizes `scheme://` and `//` with a case-insensitive scheme regex. A single leading slash is relative under this helper.
- [1] Lines 18–21 require a truthy base and either relative URL or `allowAbsoluteUrls == false`. The prompt restricts that option to boolean/absent, so unrelated loose-equality values are not a hidden requirement. No truthy base returns the requested URL even for false.
- [2] `lib/helpers/combineURLs.js:11–14` removes only a regex-matching one-or-two trailing-slash suffix, all leading relative slashes and inserts one joining slash; falsy relativeURL returns base. This is not an all-trailing-slashes regex. The complete helper is short enough to inspect, but the representative citation may remain the caller.
- [3] Those complete helper bodies show string operations, not standard URL-object resolution, dot-segment canonicalization or an origin/security rejection. Absolute URL concatenation under false is explicitly corroborated by an existing helper test.

`uri_serializer_selection`, representative `lib/helpers/buildURL.js:31–64` (34 lines; marker at 45):

- [0] Lines 33–35 return before any serializer/fragment handling for falsy params; empty truthy objects can instead serialize to an empty result.
- [1] Lines 39–50 normalize a function to `{serialize: options}` and invoke the chosen serializer with both params and options. The call is before other serialization paths and has no catch; returned strings are not re-encoded afterward.
- [2] Lines 37,51–54 distinguish native `URLSearchParams.toString()` from the Axios accumulator's `.toString(_encode)`. A custom encoder applies to the latter, not the native shortcut or a selected custom serializer.
- [3] Lines 57–64 strip the first `#` suffix and choose `?`/`&` only for a truthy serialized result. Empty/falsy output preserves the original fragment and URL. Neither unconditional fragment stripping nor query-string deduplication is implemented.

`uri_parameter_materialization`, representative `lib/helpers/toFormData.js:148–181` (34 lines; marker at 167):

- [0] `lib/helpers/AxiosURLSearchParams.js:36–55` initializes `_pairs`, delegates to `toFormData`, collects via append, encodes both pair sides and joins `key=value` entries with `&`. Supplying this append target is not multipart network dispatch.
- [1] `toFormData.js:95–108` supplies default indexes=false; 164–171 skips null/undefined flat-array elements and emits repeated `name[]`. The build walk at 201–204 skips ordinary null/undefined object members before visitor/conversion. Thus `convertValue(null)` at 117 does not cause those omitted members to become empty parameters.
- [2] `toFormData.js:39–45,116–125,175–179,192–208` covers bracket-style nested keys, recursive visits and Date/boolean conversion. Custom visitors, special key suffixes, binary/file values, cycles and non-default dot/index modes are explicitly outside this task; they must not become additional clauses.
- [3] `buildURL.js:14–19` is the selected default encoder: encodeURIComponent, restoration of colon/dollar/comma and space-to-plus. It leaves brackets percent-encoded. Its explicit passage at 37,54 into `AxiosURLSearchParams.js:48–55` distinguishes it from that file's own fallback encoder at 13–25.

## Read-only corroboration and input boundaries

Existing test bodies were inspected as supporting source, not executed:

| Test path | Raw SHA256 | Relevant inspected behavior |
| --- | --- | --- |
| `test/specs/instance.spec.js` | `f9c882606804164ba06765ff685e8a5e5252b361b198c8351304e07797145376` | getUri defaults/base/query/fragment examples at 126–159 |
| `test/specs/core/mergeConfig.spec.js` | `56a2730bb45d881b432511bca707799fb2f73fb9bfd8a6444e836aee5d10f56f` | plain merge, request-only values, undefined and copying |
| `test/specs/core/buildFullPath.spec.js` | `57c79cedb506870c02c742cdaf113500ae1b49822bc4b1422a22ee03e617dccf` | relative/absolute/false/no-base string combination |
| `test/specs/helpers/buildURL.spec.js` | `8986a3a83bff91fdfd127499ddce7318b2cf68bbb2d8ff67f0d80468e4b880dd` | null members, arrays, nested objects, dates, custom/native serializers, encoded brackets and fragments |

The complete source corpus remains available even though the representative quote is small. Native URLSearchParams, ECMAScript and dependency internals are not recreated as hidden oracles. The task assumes ordinary acyclic data and callable serializer callbacks; it does not demand validation of exotic config objects, prototype attacks, binary visitors or a successful HTTP request.

## Reuse, graph feasibility and selection bias

The repository was used in `evals/overload-token-cohort/javascript/cases.json` for request overload/interceptor behavior. Searching the local historical case catalog found no `getUri` composition question. This supports only the narrower statement that this is a newly specified operation in that reviewed catalog; the repository is reused, adjacent code is familiar and no held-out distribution claim is made.

Source-reviewed navigation candidates include `Axios.getUri -> mergeConfig/buildFullPath/buildURL` at `lib/core/Axios.js:201–203`, `buildFullPath -> isAbsoluteURL/combineURLs` at 17/19, and the visitor/accumulator handoffs described above. Existing graph inspection found the three getUri imports resolved; future acceptance still requires independent review of the exact new pinned graph. The eventual `relationships.json` must include all relevant reviewed actual edges rather than only a convenient chosen edge. Imports, a hash-bound quote or a source-only excerpt are not by themselves successful relationship delivery; static edges are not runtime-call proof.

Selection followed source and graph inspection, creating mechanism/edge-selection bias. This development comparison must retain all repetitions, prior failures, efficient ordinary-read alternatives, complete quality criteria and strict actual input AND output gates. Optional call-site delivery is a hypothesis, not a guaranteed adoption, quality improvement or token saving. Smaller serialized tool output is not an actual-model token result.
