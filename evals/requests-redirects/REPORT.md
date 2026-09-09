# Requests redirect-flow observation

This pair fails the predeclared quality-preserving token-savings gate. Both trials completed once, with one completed model turn each, under the frozen gpt-5.6-sol/xhigh configuration. Source, runtime, input hashes and archive postflight match. No retry or network request was made.

| Measure | Baseline | Columbus |
| --- | ---: | ---: |
| Total input tokens | 195,098 | 511,145 |
| Cached input subset | 153,856 | 461,696 |
| Uncached input | 41,242 | 49,449 |
| Output tokens | 10,803 | 16,987 |
| Reasoning output subset | 7,434 | 11,879 |
| Seconds | 371.723 | 603.599 |
| Completed commands | 24 | 34 |
| Command output bytes | 62,661 | 55,895 |
| Bounded citation checks | 9/11 | 8/11 |
| Predeclared semantic checks | 5/11 | 6/11 |

Columbus total input increased 161.994%, output 57.243%, and uncached input 19.900%. Smaller command output did not produce lower model usage. Counts are measured runtime usage; cached and reasoning values are subsets, not additional tokens. This is one Requests repository/task pair, not a population estimate and not a replacement for the previous Django failures.

Both answers omit response-hook ordering, default following, history/final-response rearrangement and final non-stream content consumption; the None proxy-map guard; post-send session cookie extraction; and RuntimeError in the response-consumption fallback. Baseline additionally omits missing-key handling for proxy credentials; Columbus quotes that branch and passes it. Both correctly explain the major method/body policies, rewind sentinel, origin-auth exceptions and netrc replacement. Per-finding judgments are retained in baseline-semantic-review.json and columbus-semantic-review.json. Actual quotes can substantiate omissions, but merely citing a broad range does not supply the omitted content.

The citation gate also exposes a limitation of this fixed rubric: both redirect_url excerpts contain real normalization code, but omit the particular initial previous_fragment assignment required by the predeclared marker. This is reported as a marker-coverage failure, not fabricated code. Baseline body_position and Columbus origin_auth_policy/auth_rebuild remove intervening source comments from otherwise accurate excerpts, failing the verbatim contiguous-quote requirement. No scoring rules were changed after launch. Even disregarding those citation failures, semantic completeness and total-token savings still fail.

Columbus first successfully searched three Requests declarations, then attempted the same import-like names with archive-callers. Search permits qualified suffixes, while callers requires exact stored names/IDs; the src-layout stored module names did not match. Three failed commands were followed by successful exact-ID queries. Those queries reported no resolved incoming calls for the three dynamic method targets, and the answer correctly declined to treat static source calls as proven runtime dispatch. The source fallback therefore remained necessary. These observed retries motivate investigating declaration selection and useful source access for targets with no resolved edges; they do not prove that removing retries alone would reverse the measured regression.

The graph stores 112 files, 883 nodes and 1,188 edges in a 173,816-byte XZ archive. Availability and compression are verified functionality, not evidence of model efficiency. The current skill's citation-reuse guidance and assignment nodes were present; this trial does not establish their isolated causal effect. Results, hashes, terminal checks and semantic judgments are retained alongside this report; raw traces are copied under .omx/observations/requests-redirects.

Review correction during the second observation: both body_retention answers omitted the predeclared rebuild_method-before-purge ordering. Their status-condition explanations remain correct, but the earlier reviews overlooked the ordering requirement. Semantic counts are corrected from 6/11 and 7/11 to 5/11 and 6/11. Source, prompts, answers, usage, citation results and the already-failed acceptance decision are unchanged.
