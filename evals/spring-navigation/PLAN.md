# Spring resource navigation evaluation preparation

The next proposed pair uses the pinned Spring core corpus, a substantially larger repository than the earlier Columbus package task. Spring has already been inspected during engine audits; this is a new model task, not a held-out repository claim. No model trial has started. Do not tune the previous failed multi-hop pair.

Neutral task for both conditions:

> Explain how DefaultResourceLoader chooses a resource handle for an ordinary path, a leading-slash path, classpath:, classpath*:, and a URL, and how the selected implementations open an InputStream. Include extension points and missing-resource behavior. Follow the implementation in this checkout, cite source lines for each behavior, and distinguish default behavior from overrides or externally supplied resolvers. Do not execute the project or assume all resources exist.

Independently reviewed grading requirements:

- ProtocolResolver instances are consulted first, and the first non-null result is returned. Such a custom result's opening behavior cannot be inferred universally.
- Leading slash and malformed-URL fallback use getResourceByPath. Its default implementation constructs ClassPathContextResource, a ClassPathResource subclass. This hook can be overridden.
- classpath: uses ClassPathResource; classpath*: uses the nested ClassPathAllResource. These are distinct branches.
- Parsed URLs select FileUrlResource for the file-URL predicate and UrlResource otherwise. FileUrlResource inherits the relevant input-stream implementation; do not substitute FileSystemResource behavior.
- ClassPathResource uses Class or ClassLoader/system resource streams according to its fields and throws FileNotFoundException when the result is null.
- UrlResource opens and customizes a URLConnection, returns its stream, and disconnects HTTP connections on IOException before rethrowing.
- ClassPathAllResource enumerates matching resources, opens their streams, closes already opened streams if a later open fails (preserving suppressed failures), and returns empty/single/concatenated streams for zero/one/many matches. Zero matches here do not have ClassPathResource's FileNotFoundException behavior.
- Citations must support implementation branches, inherited behavior and error behavior. Do not claim runtime completeness from missing graph edges.

`preflight.py` records source-reviewed ranges and verifies their hashes against the saved index independently of target resolution. All five principal methods are present and non-partial. The three stream-opening methods have no stored call edges, so graph-based runtime reachability is not an acceptable oracle. This task instead measures declaration/source navigation; semantic grading must use the source requirements above.

Before launching, freeze the entire source corpus, current engine/skill and cases; prepare the existing read-only observation harness; verify citations against an independent oracle; record the exact model, order, timeout and integrity hashes; and commit that executable plan. Run one baseline and one Columbus condition without selective retries or post-result prompt edits. Compare actual input, cached/uncached input and output only after both semantic and citation gates pass. Count skill overhead and all extra source reads. A successful pair would still not establish general savings.
