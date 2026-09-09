# Source review of DefaultResourceLoader targets

This census revisits the concrete navigation file named in issue #4 at Spring revision 4c8c6409a27a62ab163d3b6196ad862b7c835440. It uses the restored full candidate-grammar index from the parse-cache Spring comparison. The verifier checks all 1166 indexed source hashes, every saved runtime Python file against the current runtime, all emitted call references and corresponding edge rows for this file. The database and runtime hashes are retained in results.json. No runtime code changes or model trial were made.

The file has 78 extracted call references. All 12 emitted targets agree with source review at their represented granularity: five method targets and seven constructed class targets. This is a review of emitted targets in a deliberately selected issue file, not a blind/random sample or an independent second reviewer. It does not establish corpus-wide precision, recall, complete extraction, runtime dispatch or constructor overload accuracy.

The source review follows these declarations:

- `ClassUtils.getDefaultClassLoader()` at ClassUtils.java:226 accepts no arguments and matches the imported static receiver at DefaultResourceLoader.java:107.
- `ResourceUtils.toURL(String)` at ResourceUtils.java:413 accepts the String location at line 177; `isFileURL(URL)` at line 282 accepts the resulting URL at line 178.
- `StringUtils.applyRelativePath(String, String)` at StringUtils.java:710 matches both calls at lines 282 and 310: inherited `getPath()` returns String and relativePath is declared String.
- The seven `new` expressions name ClassPathResource, FileUrlResource, UrlResource, or one of the two nested ClassPath resource classes. Imports/package and lexical nesting agree with the emitted class nodes. The graph does not identify their selected constructor overloads; these seven matches must not be added to a method-overload precision denominator.

Three source-reviewed omissions remain explicit in results.json: `getProtocolResolvers()` at line 158 refers to the local declaration at line 129; the enhanced-loop variable is declared ProtocolResolver and its call at line 159 has static interface declaration `ProtocolResolver.resolve(String, ResourceLoader)`; `getResourceByPath(location)` at line 166 refers to the local protected declaration at line 198. These are static declaration expectations, not claims about overriding runtime implementations. Current reasons are unsupported loop scope for the first two and inherited candidate applicability for the third. The other unresolved references were not individually graded, so 12/78 is not reported as recall.

This evidence confirms useful but incomplete navigation in the exact issue scenario. Supporting enhanced-loop bindings alone would not address the separate inherited-call limitation. Broader resolver work needs scoped bindings and negative fixtures; returning plausible candidates as resolved edges would not satisfy the issue.

Reproduce against the retained source/index/runtime:

```sh
.venv/bin/python evals/resource-loader-targets/verify.py \
  /tmp/columbus-cache-reuse-spring/after/source \
  /tmp/columbus-cache-reuse-spring/after/index.sqlite \
  /tmp/resource-loader-targets.json \
  --runtime /tmp/columbus-cache-reuse-spring/after/runtime
```

The temporary full index is not committed. Its producer and full initial/edit/restore parity receipts are in `evals/parse-cache-reuse/`; the compact reviewed expectations and verification results are committed here.
