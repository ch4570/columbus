# Saved-archive capfirst observation

No accepted token-savings result. The baseline completed but omitted three predeclared semantic details. Columbus timed out without a final answer or usage event. Missing usage is unknown, not zero; no token reduction percentage can be computed.

The task, source, runtime, skill, oracle and grading criteria were committed at d7f93e32da401011c84c42e1e1fbeaba46a6c206 before either run. Baseline ran first, then Columbus, once each, requested gpt-5.6-sol/xhigh with a 600-second limit. No replay or prompt tuning occurred. Backend identity is not independently attested. This is a new target on the same Django snapshot as earlier observations, not an independent repository sample.

| Measurement | Baseline | Saved XZ graph |
| --- | ---: | ---: |
| Elapsed seconds | 361.567 | 603.108 (timeout handling included) |
| Input tokens | 221,419 | unavailable |
| Cached input tokens | 183,936 | unavailable |
| Uncached input tokens | 37,483 | unavailable |
| Output tokens | 10,499 | unavailable |
| Commands | 40 | 42 |
| Command output bytes | 90,641 | 101,160 |
| Exact caller set and citations | pass | fail: no answer |
| Predeclared semantic criteria | fail | fail: no answer |

Baseline correctly identified all 14 lexical callers and covered their 22 syntactic calls. Its answer omitted the extra_context override in history_view, initial date-range inference in date_hierarchy, and the no-browser skipped-class result in SeleniumTestCaseBase.__new__. These were in the committed SOURCE-REVIEW.md, so this report does not weaken the gate to accept the otherwise useful answer. semantic-review.json records the per-caller assessment.

Columbus read the frozen skill and archive reference, ran archive-search, and used incoming calls from archive-neighbors. It first requested offsets 0 and 16, then recovered with 8 and 15, adding an unnecessary overlapping page. It also used rg, source hashes, and bounded source excerpts, followed by another set of quote reads. All recorded commands returned successfully. The timeout produced return_code 0 after termination handling, but timed_out is true and answer is empty; the return code is not evidence of task completion. The logs do not establish why final generation stalled, and this run cannot attribute the timeout to XZ decoding alone.

Both preflight and postflight checks passed: all 6,928 supplied source-file hashes and frozen runtime hashes were unchanged, the saved artifact checksum was unchanged, and no consumer .columbus or .repoatlas index existed. The archive contains 5,465 indexed files, 46,630 nodes and 86,828 edges. Independent AST comparison checks all 883 Python files under django/ and confirms the target's 22 production call sites with multiplicity. The full incoming archive inventory also contains one top-level test call, excluded by task scope.

The frozen XZ artifact is 8,592,888 bytes. Producer indexing took 17.856 seconds and archive export took 7.445 seconds, recorded separately from model usage. These are individual local observations, not amortized performance claims. The standalone original-checkout gzip/XZ receipts differ slightly in size because its index includes tests/.coveragerc; production-source parity is verified in both snapshots.

The shared harness passed 18 tests. Portable distribution CI 34165579061 passed all six Linux/macOS/Windows × Python 3.11/3.14 jobs at the declaration commit. Raw trial evidence is retained under .omx/observations/archive-capfirst locally; results.json stores answers, command metadata, usage when available, and event hashes. input-hashes.json and post-run.json establish frozen grading inputs and postflight checks.

The saved graph is usable without consumer SQLite, but this trial does not establish more efficient model exploration. The next engineering investigation should measure archive pagination overhead and repeated source retrieval independently of this completed pair. Preserve this timeout and the previous unsuccessful pairs; any future model task needs a new declaration.
