# Django caller trial: accurate, but higher token usage

Both answers passed the exact 12-caller set, contiguous bounded citation checks and manual behavior review covering all 15 production call sites. Columbus used its actual graph `callers` command, but did not reduce tokens in this single pair.

| Metric | Baseline | Columbus |
| --- | ---: | ---: |
| Input tokens | 69,777 | 110,525 |
| Cached input subset | 51,072 | 85,504 |
| Uncached input | 18,705 | 25,021 |
| Output tokens | 5,280 | 8,313 |
| Reasoning output subset | 2,342 | 4,585 |
| Wall seconds | 180.722 | 283.728 |
| Shell commands | 14 | 20 |
| Command output bytes | 28,519 | 38,324 |

Input increased 58.40%, uncached input 33.77%, and output 57.44%. No savings claim is supported. This was one baseline-first pair with requested gpt-5.6-sol/xhigh, a 600-second limit per condition, no model retries, and the declaration committed at 292d913. Actual backend identity is not independently attested. The initial harness invocation used the nonexistent `trial` subcommand and exited at argument parsing; the corrected `run` invocation created the first and only baseline model process. Both model processes subsequently exited successfully before timeout.

The Columbus condition read the skill, called `callers iri_to_uri` with a 12,000-byte budget, then performed a production-name search and additional bounded source reads. The graph response contained all 16 stored lexical callers including tests and was not truncated. Short call-site excerpts identify edges but do not provide all surrounding branch conditions, lazy-property comments or the multiple feed fields needed for this explanation task. Additional context was therefore useful; this observation suggests improving bounded caller context and path filtering, not merely instructing agents to stop verifying. It does not isolate a causal token cost for any individual command, and no change to the frozen task was made after observing answers.

Frozen cold indexing took 17.436 seconds, separate from model latency and usage. The 883 production file hashes and independent call oracle passed before trials. After both trials, all source/runtime manifests, SQLite bytes, harness, schema, case catalog and review criteria still matched their pre-run hashes. results.json retains answers, command receipts and runtime usage; semantic-review.json records the manual review; raw events and invocation receipts are copied under .omx/observations/django-callers and their hashes are retained in results.json. The temporary original trial directories also remain available.

Archive size and paging parity are independently documented in SOURCE-REVIEW.md and frozen-graph.json. These support portable storage and graph correctness for this target; they do not establish token savings or completeness across repositories. The requested overall goal remains incomplete.
