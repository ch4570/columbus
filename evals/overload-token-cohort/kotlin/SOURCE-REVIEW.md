# Kotlin RequestBody overload source review

Prepared before model execution for `kotlin-request-body-overloads`. This is a source-reviewed saved-archive task, not an evaluation of local receipt continuation. No target code, tests, builds or model trials were executed in this review. Freeze this catalog, criteria and review together with the cohort protocol, harness/schema, runtime/skill, source corpus, recognizer and collector before any trial. Historical cohorts and their criteria remain unchanged.

## Pinned corpus and provenance

- Requested repository: [square/okhttp at the pinned commit](https://github.com/square/okhttp/tree/d4e7006216ddf06ffe628d1320b62ac01843b63d). On review, that GitHub page redirected to [lysine-dev/okhttp at the same commit](https://github.com/lysine-dev/okhttp/tree/d4e7006216ddf06ffe628d1320b62ac01843b63d).
- Commit: `d4e7006216ddf06ffe628d1320b62ac01843b63d`.
- Requested and observed final ZIP URL: `https://codeload.github.com/square/okhttp/zip/d4e7006216ddf06ffe628d1320b62ac01843b63d`. The ZIP request itself did not redirect; do not substitute the repository-page redirect for the observed download URL.
- ZIP SHA-256: `0d15e84d42a532c9ba5df19024ecc3bd64792e63c72264c068f30455c60a87e4`; compressed ZIP size: **2,931,580 bytes**.
- Complete superproject ZIP: **844 files / 7,913,379 uncompressed bytes**, after stripping the single top-level directory. The earlier prospective note's 2,931,580-byte figure is the ZIP size, not the extracted source size. Retain every ZIP file, not an evidence-only subset.
- The nontruncated GitHub recursive tree has exactly the same 844 blob paths. All ZIP file Git blob hashes match except `gradlew.bat`, whose export uses CRLF as directed by `.gitattributes`; its ZIP size is 2,848 bytes versus the 2,766-byte Git blob. The tree blob total is therefore 7,913,297 bytes. The frozen corpus is the pinned ZIP, not a claim that every exported byte equals the Git blob.
- This is not a recursive submodule checkout. The tree's unrelated HPACK test-data gitlink `okhttp-hpacktests/src/test/resources/hpack-test-case` is intentionally omitted by the archive. Its commit is `8a1406e7d14bfcb6c046021f13cc15cfb162726d`; `.gitmodules` identifies `https://github.com/http2jp/hpack-test-case.git`. No task clause depends on it.
- `LICENSE.txt`: Apache-2.0; SHA-256 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`.

The ZIP hash, inventory, raw file hashes and physical source lines were independently checked from downloaded bytes in memory. The GitHub tree confirmed blob-path completeness and the omitted gitlink. Browser-rendered text can collapse blank lines; the anchors below use decoded raw bytes split into physical lines instead.

All reviewed Kotlin paths below are relative to `okhttp/src/commonJvmAndroid/kotlin/okhttp3/`:

| File | Physical lines | SHA-256 |
| --- | ---: | --- |
| `RequestBody.kt` | 274 | `1f998aafeaf38c3cbc922e9a3726b3f61c41b88e4e3989307ef7315427055e1a` |
| `internal/internal.kt` | 122 | `06a3412357a0fe8931a7d4034c17386ebf298a38e0dab2d6e916f7b3a38d2aa1` |
| `MediaType.kt` | 186 | `60a3cd4bf933069135c383294874c11995a51fe99a84a82582b893b0b4f2f337` |
| `internal/-UtilCommon.kt` | 399 | `66fbb341c0c93444674f3d4c7b6d0015652faaf2c2d9f7be18908e8b025ae3e8` |

## Citation and semantic contract

`cases.json` asks explicitly for all four legacy mappings, content type/byte length/writes, the charset fallback append nuance, array defaults/bounds/retention, and File length/resource/one-shot behavior. Descriptions identify the representative mechanism for each finding without exposing private paths, markers or line numbers in the prompt. `criteria.json` is the full semantic oracle.

Require each requested finding ID exactly once, every unchanged source-citation rule, and every positive semantic clause for both arms. Missing facts, contradictions, unexpected findings or duplicate findings fail. Prohibitions constrain contradictions; answers need not recite unrelated warnings. Scope exclusions are boundaries, not additional mandatory facts. The graph is navigation evidence, not the semantic oracle; missing edges do not excuse missing behavior.

One bounded contiguous verbatim representative quote per finding is sufficient. Other reviewed helper/base-class behavior can be established in the explanation without requiring every clause to fit that same quote. A range alone does not establish prose the answer omitted. Do not stitch excerpts, insert ellipses, or exceed 40 physical lines. In particular, all four legacy declarations span 221–272 (52 lines), so they are split into two neighboring pairs instead of imposing an impossible single citation.

| Finding | Representative file/range | Lines | Oracle call line |
| --- | --- | ---: | ---: |
| `legacy-string-bytestring` | `RequestBody.kt` 221–239 | 19 | 239 |
| `legacy-array-file` | `RequestBody.kt` 252–272 | 21 | 272 |
| `string-encoding` | `RequestBody.kt` 124–128 | 5 | 127 |
| `charset-policy` | `internal/internal.kt` 93–106 | 14 | 100 |
| `array-slice` | `RequestBody.kt` 163–178 | 16 | 168 |
| `bytestring-body` | `RequestBody.kt` 132–141 | 10 | 139 |
| `file-body` | `RequestBody.kt` 183–192 | 10 | 190 |

These are valid representative ranges, not mandatory exact start/end choices. Each covers its literal private marker and reviewed call line. The legacy descriptions require both mappings in prose but name the second delegate (ByteString or File) as the representative citation; narrower ranges covering that named delegate also suffice. The frozen grader checks a required marker and at least one listed call line; semantic review must still check both mappings and all other required facts. Keep this review, paths/markers, criteria and source metadata out of the model prompt and source corpus.

## Reviewed mechanisms and cautions

### Legacy String and ByteString mappings

`RequestBody.kt` 211–239 declares both content-type-first compatibility functions and deprecation guidance. String delegates to `content.toRequestBody(contentType)` at 224; ByteString does so at 239 with a different receiver type. The replacement uses the content receiver in Kotlin and content first for Java calls. Their common Kotlin/JVM names do not erase receiver distinctions. The representative 221–239 range covers both mappings; annotations and Java migration wording also have support at 211–219 and 226–234.

### Legacy ByteArray and File mappings

`RequestBody.kt` 241–272 contains the other pair. The array delegate at 257 forwards media type, offset and byteCount unchanged, with defaults 0 and `content.size`. The File delegate at 272 calls `file.asRequestBody(contentType)`. Array/file-first replacement guidance is in the adjacent deprecation annotations. Do not confuse File with the separate Path or FileDescriptor extensions.

### String pipeline

`RequestBody.kt` 124–128 calls `chooseCharset`, encodes with the chosen charset, then delegates the resulting byte array with the final nullable media type, offset 0 and `bytes.size`. Its body length and write behavior follow the ByteArray implementation at 163–178. Encoded byte length is not necessarily String character count.

### Charset fallback and append precedence

`internal/internal.kt` 93–106 starts with UTF-8 and the original nullable media type. Null stays null. A non-null supported charset is retained with the original type. Missing or unresolvable charset instead selects UTF-8 and assigns the result of parsing the original type text plus `; charset=utf-8`.

`MediaType.kt` 44–51 obtains the charset parameter and catches `IllegalArgumentException` from `Charset.forName`, returning its default (null for this caller). At 57–64, parameter lookup takes the first matching name, ignoring case. Parsing preserves parameter order at 112–149; `toMediaTypeOrNull` catches parse `IllegalArgumentException` and returns null at 155–160.

The code appends, not replaces. For a parsed media type whose first charset is unsupported, the appended UTF-8 parameter need not change subsequent `charset()` resolution: lookup still sees the first unsupported value even while the String body bytes use UTF-8. Do not assert that augmentation guarantees a type reporting UTF-8 or that unsupported charset alone throws here. Nullable parsing is the implemented branch contract; the rubric does not require constructing a malformed internal MediaType or claiming an ordinary valid type necessarily triggers parse failure. Charset support is runtime-dependent; no fixed exhaustive charset list is required.

### ByteArray defaults, bounds and ownership

`RequestBody.kt` 163–178 defaults byteCount to size, not size minus offset, invokes bounds validation before allocating the anonymous body, preserves media type, reports byteCount as Long, and captures/writes the original array slice. A positive offset with omitted count fails rather than selecting the remaining suffix. Later mutations to the selected slice can affect writes; there is no defensive copy.

`internal/-UtilCommon.kt` 372–380 rejects negative offset/count, offset beyond array length, or count exceeding the remaining length with `ArrayIndexOutOfBoundsException`. Exact exception text is out of scope, including the apparent repeated-offset value in its message. No target execution or mutation experiment is needed to establish these source-level facts.

### ByteString body

`RequestBody.kt` 132–141 preserves the supplied nullable media type, reports size as Long and directly writes the ByteString receiver to the sink. It does not use String charset selection or reinterpret bytes from a media-type charset. Deeper Okio storage/copy mechanics are not part of the task.

### File body and base contracts

`RequestBody.kt` 183–192 preserves media type and calls `File.length()` from each contentLength query. Each write opens a source and copies it inside `use`; standard Kotlin resource ownership closes that successfully opened source when the block exits, including after copy failure. The sink is not the resource owned by this `use`. The base writeTo contract at 44–46 says not to close the sink.

The complete File anonymous body at 183–192 has no isOneShot override; the inherited implementation at 99 returns false. Do not import the different FileDescriptor override into File. This does not promise a content snapshot, identical bytes across writes, successful reopening, or network-level replay safety. File contents/length can change between calls. No detailed filesystem failure taxonomy, network retry behavior, Okio internals, Path or FileDescriptor trace is required.

## Evidence limits

This is one pre-reviewed Kotlin/JVM implementation task on one pinned superproject archive, not a held-out repository claim, a compiler/runtime proof, or a universal token-savings claim. The larger new cohort's fixed order and actual input/output/quality gates apply separately. Source review supplies the semantic oracle; no model answer was used to adjust these requirements.
