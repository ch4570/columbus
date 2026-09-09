# Conditional escape trial: no token savings

The Columbus answer passed exact caller-set, citation and manual semantics review for 12 callers and 13 direct call sites. The baseline had the correct callers and explanations but failed one citation: format_html_join's quote extends through line 171 while its declared range ends at 170. Preserve that failure; no answer was repaired or replayed.

| Metric | Baseline | Columbus |
| --- | ---: | ---: |
| Input tokens | 52,873 | 171,833 |
| Cached input subset | 33,536 | 146,688 |
| Uncached input | 19,337 | 25,145 |
| Output tokens | 6,901 | 9,128 |
| Reasoning output subset | 3,837 | 5,343 |
| Wall seconds | 229.436 | 309.382 |
| Shell commands | 17 | 10 |
| Command output bytes | 32,624 | 35,248 |

Input increased 224.99%, uncached input 30.04%, and output 32.27%. The pair also fails the predeclared both-answers-quality gate. It supplies no accepted savings result. Fewer shell commands do not imply fewer input tokens; retain the actual runtime usage rather than substituting command counts or byte estimates.

Columbus read the skill and used both --path and --context-lines. Its first callers query supplied a module-qualified target name, unsupported by the frozen caller lookup, then searched for the exact symbol ID and successfully retrieved callers with a 20,000-byte budget and 20 context lines. It also performed source searches and supplementary reads. These observations identify lookup usability and remaining context costs; they do not quantify their individual causal contribution to tokens.

The declaration was committed at 5535121. Both conditions ran once, baseline first, requested gpt-5.6-sol/xhigh with 600-second limits. Both terminated successfully without timeout. Backend identity is not independently attested. This is a second target on the same repository, not an independent population sample. Full source/runtime manifests, SQLite bytes, harness/schema/case/review hashes remained unchanged. A concurrent Windows-only fixture encoding correction did not alter frozen inputs. Raw trials are retained in .omx/observations/django-html-callers; results.json contains answers, command receipts, usage and raw-event hashes. semantic-review.json contains the separate quality review. No price or generalized efficiency claim is made.

The overall goal remains incomplete. Graph storage and same-line correctness have evidence, but actual model savings have not been established. Further work should address observed retrieval overhead and validate it on a separately declared task without rewriting these results.
