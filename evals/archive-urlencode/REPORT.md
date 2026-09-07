# Scoped urlencode saved-archive comparison

No accepted overall token-savings result. Both answers found the exact seven callers and passed citation checks, but the graph answer misstated the synchronous request's empty-encoded-result fallback. Its uncached input decreased 30.31%, while total input increased 46.29% and output increased 5.58%. Preserve all three measurements rather than presenting the favorable subset as the result.

The task, independent AST oracle, semantic review criteria and frozen runtime/source/skill were committed at d335aca before either model started. Baseline ran first, then Columbus, once each, requested gpt-5.6-sol/xhigh, with a 600-second limit. Both completed; no replay, tuning or timeout extension occurred. Backend identity is not independently attested. This is a different target on the same Django repository, not an independent population sample.

| Measurement | Baseline | Saved graph |
| --- | ---: | ---: |
| Elapsed seconds | 441.208 | 495.087 |
| Total input tokens | 379,707 | 555,486 |
| Cached input tokens | 321,536 | 514,944 |
| Uncached input tokens | 58,171 | 40,542 |
| Output tokens | 12,594 | 13,297 |
| Reasoning output tokens (subset) | 8,259 | 7,503 |
| Commands | 13 | 24 |
| Command output bytes | 127,927 | 77,246 |
| Exact caller identities/citations | pass | pass |
| Reviewed behavior | pass | fail |

Baseline correctly describes that RequestFactory.generic falls back to the URL query even after an executed encoder returns an empty string. The graph answer instead says truthy query_params takes precedence over the URL and describes fallback only for falsy query_params. A truthy mapping containing an empty sequence can encode to an empty string with doseq=True. Its quoted source contains the correct condition, but does not repair that misleading prose. The asynchronous method intentionally has different if/elif behavior. semantic-review.json records per-caller judgments and the distinction between a quote substantiating an omitted detail and contradicting prose.

The graph agent read the skill/reference, initially attempted unsupported `archive-search --format text`, inspected help, then retried successfully. It used one scoped incoming-call query with `--path 'django/*' --context-lines 4 --format text --budget-bytes 20000`; that query returned all seven calls with verified source in 8,738 bytes. It then performed further import checks, broader control-flow reads and repeated numbered reads for quotations. Therefore routing, path filtering and source context were actually used, but they did not eliminate follow-up work. The unsupported search-format attempt is a concrete interface inconsistency for subsequent work; do not replay this pair after fixing it.

Baseline independently chose a broad import search that emitted 62,562 bytes in one command, contributing substantially to its larger command-output and uncached-input totals. It was not instructed to dump the repository. This observation is therefore not a claim against every efficient search strategy. The graph condition made more commands and accumulated 193,408 additional cached-input tokens, offset by 17,629 fewer uncached-input tokens. Command bytes and uncached input alone do not characterize total model usage. No monetary savings are computed.

Both source/runtime manifests and saved-archive pre/postflight gates passed. The archive checksum remained 628c02774deaef31a5dc16fde0d7f97565280e69809dd4f9196b700ac35482be and neither consumer index directory existed. The archive contains 5,465 indexed files, 46,630 nodes and 86,828 edges; all 6,928 supplied source-file hashes were verified. Independent AST/source checks cover all 883 Python files under django/ and the seven scoped callers. The complete incoming graph has 27 edges, including 20 out-of-scope test calls; the filter excludes those before pagination.

Producer indexing took 17.089 seconds and XZ export took 7.333 seconds, separate from model usage. The saved archive is 8,592,888 bytes. The first preparation at /tmp/columbus-archive-urlencode-frozen remains unchanged; the model pair used /tmp/columbus-archive-urlencode-trial with the newer scoped runtime. Raw model evidence is retained locally under .omx/observations/archive-urlencode, with event hashes, answers, usage and commands in results.json. Grader/harness/schema hashes remain unchanged. The path-filter implementation at 86fbf47 also passed all six distribution jobs in run 34167913253, retained in ../archive-path/platform.json.

The storage and retrieval features are functional. The remaining objective requires correct completed answers with improved overall model usage, plus the separately tracked JVM/issue acceptance work. This pair provides evidence about uncached-input reduction and interface/repeated-reading costs, not completion of that objective.
