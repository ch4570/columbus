# Java resource-handle navigation: prospective source rubric

This is a source-reviewed development comparison, not a held-out operation. No models, repository code, tests or builds were run to prepare this rubric. All 5 findings and 18 zero-based criterion clauses in `criteria.json` are mandatory. Source evidence elsewhere in the same answer, including complete quoted implementation, may support a clause; contradictory prose fails the affected clause. A representative quote is not required to squeeze every cross-file explanation into one range. The cited range must contain the private marker and cover at most 40 physical lines. The quote may be a contiguous subrange within that citation; matching ignores indentation only, with no stitching, and does not separately require the quote itself to include the marker. Paths, markers and these review notes are private grading data, not prompt additions.

## Source identity and scope

The complete existing 1,166-file `spring-core/` module fixture is used, not just the files below and not the complete multi-module Spring repository. Its ZIP SHA256 is `68572527bfad750c2ab2c55dcbab1324568a4584d0d122cc3a4dfac8c139bd0c`; all 1,166 ZIP file paths and bytes were independently matched against the local source snapshot. The inventory SHA256 is `53bd4243666ca2f8ad02a3f00b349dd565ac10f1df889e8041bc4c1b87753143`; encoding, local paths and provenance limits are in `../sources.json`.

Upstream pin: [Spring Framework 4c8c6409a27a62ab163d3b6196ad862b7c835440, spring-core](https://github.com/spring-projects/spring-framework/tree/4c8c6409a27a62ab163d3b6196ad862b7c835440/spring-core). The existing module ZIP is not a newly retrieved codeload archive. Apache-2.0 source headers are retained; the repository-root `LICENSE.txt` is outside this module fixture, as disclosed in `sources.json`.

Production paths below are relative to `src/main/java/org/springframework/`:

| Path | Bytes / physical lines | Raw SHA256 |
| --- | --- | --- |
| `core/io/DefaultResourceLoader.java` | 10249 / 315 | `a80386107541683cd5f929e479be638ad2821d1a2cb0d7518225b2740e62801c` |
| `core/io/ClassPathResource.java` | 9152 / 286 | `c8157b437588b1860a7dbf2380752f721566a550a82f44aeb65fc4b426750e96` |
| `util/StringUtils.java` | 50999 / 1452 | `5e262ad37b676f032bb3f8958a5b842ea81e7b4f49f0b39af04ed92adda09d81` |
| `util/ResourceUtils.java` | 17121 / 458 | `487bad25214de61816624e2a92a31409ad62863c3df72e1eb1e82d4073ae364d` |

## Clause-to-source review

`resource_location_routing`, representative `DefaultResourceLoader.java:154–185` (32 lines; marker at 177):

- [0] Lines 156–163 establish validation, ordered resolver calls and first non-null return; field initialization at 64 and registration at 118–120 establish ordinary `LinkedHashSet` registration behavior.
- [1] Lines 165–172 distinguish slash, `classpath:` and `classpath*:` branches. The default path hook at 198–199 returns `ClassPathContextResource`, not a filesystem handle.
- [2] Lines 175–183 establish URL construction, classifier handoff and the specific `MalformedURLException` fallback. `ResourceUtils.java:282–285` classifies `file`, `vfsfile`, `vfs`; its `toURL` implementation is at 413–422. The rubric stops at this helper boundary and does not require its complete URI-constructor fallback algorithm.
- [3] The default routing constructs handles without a lookup/open call. A resolver's earlier return can replace any built-in route; this is not a claim about externally supplied resolver side effects or all loader subclasses.

`classpath_coordinates`, representative `ClassPathResource.java:110–125` (16 lines; marker at 121):

- [0] Lines 70–71 and 84–94 establish ClassLoader-constructor delegation, validation, cleaned/slash-adjusted stored coordinates and loader selection.
- [1] Lines 110–125 distinguish stored class-relative `path` from derived `absolutePath`. Notably a null `clazz` leaves both context fields null; the later lookup falls back to a system resource. Do not replace observed implementation with the constructor Javadoc's broader default-loader wording.
- [2] Lines 135–143 expose absolute path/context; `DefaultResourceLoader.java:84–107,169,198–199` selects and passes a loader when creating a handle. No field is dynamically re-selected by each ClassPathResource read.
- [3] `StringUtils.java:724–731,735–815` documents and implements lexical cleaning and explicitly warns against a security interpretation. Dot/parent suppression and slash normalization suffice; no full algorithm reproduction is demanded.

`classpath_url_lookup`, representative `ClassPathResource.java:173–190` (18 lines; marker at 182):

- [0] Lines 175–183 distinguish Class/path, ClassLoader/absolutePath and system/absolutePath.
- [1] Lines 185–188 implement only the `IllegalArgumentException` suppression. `exists` at 153–154 returns a null test; `getURL` at 224–229 throws `FileNotFoundException` on null.
- [2] These bodies do not open/retain a stream; stream access is an independent method at 200–215. An existing URL is not proof of future access success.

`classpath_stream_access`, representative `ClassPathResource.java:200–215` (16 lines; marker at 209):

- [0] Lines 202–210 make three direct stream calls using the same context priority but not the URL helper.
- [1] Lines 211–214 check null, throw `FileNotFoundException` or return the stream. No URL-helper catch is present in this method.
- [2] The complete body has no close, stream cache or content cache. This statement is local to the method and does not assert behavior inside JDK/resource-loader implementations.

`classpath_relative_handles`, representative `ClassPathResource.java:238–242` (5 lines; marker at 239):

- [0] Lines 239–241 use stored `path` and preserve Class or stored ClassLoader when constructing a new handle.
- [1] `StringUtils.java:710–721` keeps the directory before the last slash, conditionally inserts a slash and appends relativePath; absent a base slash it returns relativePath. A relative argument beginning `/` does not discard an existing directory prefix here.
- [2] Constructor calls re-enter cleaned coordinate setup at `ClassPathResource.java:84–94,110–125`, without opening or checking resources.
- [3] `DefaultResourceLoader.java:297–311` defines `ContextResource`, `getPathWithinContext -> getPath`, and subtype-preserving relative construction based on `getPath`/`getClassLoader`.

## Read-only corroboration and limits

`src/test/java/org/springframework/core/io/ClassPathResourceTests.java` (9902 bytes, 262 physical lines, SHA256 `0c4bd47792cb4d837edf2526c734128588a4a8548796f8d3aec79259b9c3aac9`) corroborates cleaned/class-relative coordinates, relative handles and missing stream behavior in its named test bodies. These tests were inspected, not run; they do not establish a live classpath or network result. The implementation is the oracle. No invented `DefaultResourceLoaderTests.java` is assumed to exist at this pin.

The prompt explicitly excludes `classpath*:` aggregation internals, URL connection behavior, `isReadable`, caches and equality. They must not become hidden semantic requirements. The new ranges clarify scope; they do not revise any historical answer or score.

## Reuse, graph feasibility and selection bias

`evals/spring-navigation/cases.json:6` already asks how the same loader routes ordinary/slash/classpath/classpath-all/URL inputs and how selected implementations open streams. This task substantially reuses that measured operation, with additional coordinate/relative-handle detail and a different scope boundary. The public corpus is reused as well. It is not accurate to call the task, operation or repository held-out. Historical failures and their original rubrics remain unchanged.

Potentially useful source handoffs include `getResource -> ClassPathResource` at `DefaultResourceLoader.java:169`, URL helper/class construction at 177–178, and `ClassPathResource.createRelative -> StringUtils.applyRelativePath` at 239. These are source-reviewed navigation candidates, not a frozen acceptance-edge list. Constructor graph targets may be class nodes, receiver/dynamic calls may be missing, and heuristic resolution is not runtime dispatch proof. The eventual pinned graph's relevant actual edges must be reviewed separately in `relationships.json`; unresolved edges cannot receive delivery credit. A source quote alone is not graph-relationship evidence.

This operation was selected after observing graph/source structure, so there is mechanism/edge-selection bias. Keeping all relevant reviewed edges, ordinary repository-read alternatives, all repetitions, full semantic/citation quality and the strict actual-input AND actual-output gate avoids concealing that limitation; it does not remove it. Optional call-site/source delivery is a hypothesis, not a demonstrated saving or a demand in the neutral user question.
