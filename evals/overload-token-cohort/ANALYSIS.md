# Actual-token result: no accepted pair

All twelve predeclared executions completed with return code 0, no timeout and one completed model turn each. **Zero of six pairs reduced both actual total input and actual output.** This remains true before considering the separate citation and semantic failures. The cohort does not satisfy main/release PR #12's gate.

No run was retried, dropped, replaced or assigned zero usage. Sources, prompts, complete clause criteria, runtime/skill and protocol remained frozen throughout. The 108-file input manifest retains SHA-256 `f6394e9832690454024cf21728f10cba5933623f12ae3858f52dfb842f49914c`. Historical failed cohorts and their hash manifests are unchanged.

## Measured pairs

B = efficient ordinary source exploration; C = the frozen Columbus package/skill with saved archive. Input includes its cached subset; output includes reported reasoning. Commands are descriptive, not the acceptance metric.

| Task / repeat | B input | C input | B output | C output | Commands B → C | Both lower? |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| java 1 | 219,005 | 190,867 | 9,976 | 11,924 | 16 → 9 | No |
| java 2 | 283,838 | 286,351 | 12,538 | 12,536 | 14 → 9 | No |
| kotlin 1 | 133,095 | 317,700 | 8,301 | 8,858 | 15 → 17 | No |
| kotlin 2 | 156,857 | 152,132 | 7,723 | 10,393 | 12 → 17 | No |
| javascript 1 | 137,650 | 99,214 | 8,055 | 8,813 | 11 → 9 | No |
| javascript 2 | 75,690 | 131,895 | 5,916 | 8,269 | 7 → 9 | No |

The predeclared gate is per pair, with no cross-pair compensation. For descriptive context only, totals are input 1,006,135 → 1,178,159 (**+17.1%**) and output 52,509 → 60,793 (**+15.8%**). Commands decrease 75 → 70. Uncached input alone decreases 233,143 → 231,343; this does not satisfy the required total-input reduction and is not a billing estimate.

The reported reasoning-output subset increases 33,978 → 41,322, accounting arithmetically for 7,344 of the 8,284 additional output tokens. This does not causally allocate token changes to individual commands, tool packets, or features. Model aliases, provider behavior and reasoning are not controlled backend attestations.

## Quality and execution findings

Mechanical citation checks pass in 6/12 answers. Java baseline1 and Columbus2 contain literal closing braces outside their declared end lines; Columbus1 and baseline2 pass all six citations. All four Kotlin answers pass seven citations each. All JavaScript answers fail at least one citation requirement: invented statements, closing braces outside the stated range, or a missing required finding.

Independent reviews retain every frozen clause and explicit command-boundary checks. All four Java answers pass their 20 semantic clauses; this does not waive the two citation failures. Across the four Kotlin answers, the same two positive charset-policy details are missing: the named charset lookup/exception mechanism and case-insensitive parameter-name matching. The helper quotes do not establish those MediaType implementation details. The four JavaScript answers omit the predeclared absent/already-null eject no-op detail; Columbus2 additionally lacks the required response_boundary finding, even though related behavior appears elsewhere. Reading relevant code in a command trace is not a substitute for final-answer coverage. Exact per-clause reasons, hashes and final status are in each language's semantic/ files and the computed results.json/REPORT.md.

These quality failures are independent of token failures. Correct prose does not waive a wrong verbatim quote/range, and a small or incomplete answer cannot count as a savings result. The supplied repository evidence and frozen Columbus evidence were the allowed sources; no target tests/builds or web research were part of the model tasks.

## What the traces actually support

- Gson overload grouping successfully retrieves eleven declarations in one command. Both Java Columbus runs use nine commands, versus sixteen/fourteen for baseline, but neither reduces both token totals. Subsequent ordinary reads still revisit portions of already-delivered source and inspect helper behavior.
- Each Kotlin Columbus run makes seventeen commands and one unsuccessful mixed-receiver overload query. The declarations share an owner/name but have distinct receiver identities; rejecting their combination is correct. Exact-ID batching subsequently succeeds. The failed lookup is an efficiency/usability observation, not a protocol violation or proof of unsound grouping.
- JavaScript Columbus2 contains a broad regular-expression search with an empty alternative and omits one final finding. Offering compact archive output does not guarantee disciplined search or complete reporting.
- This cohort measures the complete frozen saved-archive package/skill on three tasks, not isolated causal feature effects, not receipt-backed local continuation, and not universal language or repository behavior. Cold index/export work is separately recorded; it is not included in model token totals.

## Follow-up and release boundary

[PR #15](https://github.com/ch4570/columbus/pull/15) makes the Kotlin receiver conflict actionable: a bounded escaped receiver list, the same-owner-and-receiver rule, and guidance to batch selected exact IDs. Grouping/selection semantics remain unchanged. It was developed in an isolated worktree while these trials continued and merged into development at `a4271c21b134fca042c17f9f2c659352382f3e39`. Its exact-head twelve platform checks, 294 local engine tests, and the merge's twelve platform checks pass. **That newer runtime was not used by this cohort and has no measured token-savings claim here.**

The cohort's frozen runtime is `588f2db846fff7036eff95a0d917277d225ae734`; protocol commit is `c4ee65c25d40c8085ee659df1da67df651c66b74`. Development evidence and usability improvements may merge; main/release remains gated. Do not relabel this result as accepted merely because a later functional improvement passes tests.

## Retention and reproducibility

All original runner handles were observed to completion: Java 97841, Kotlin 93576, JavaScript 68234. A single retention run then verified all twelve terminal results, original events and frozen inputs before publishing 135 files. RETENTION.json SHA-256 is `2bcd242876ec7d40d5e185b17a50d28141d9c9f35bfa55cd90961f9d567f7452`.

retained/ preserves original prompts, invocations, process metadata, stderr, answers/results, exact per-language XZ archives and one byte-identical shared runtime. The manifest retains all original runtime paths. Each events.jsonl.gz decompresses to the exact original event hash. Complete source ZIPs and their licenses remain under each language directory. Failed answers are retained, not repaired.

The immutable collector expects the original observation paths/interpreter and matching frozen inputs; retention is not a portable path-rewriting replayer. Use the evaluation branch's final pre-merge head (which descends from the protocol commit) for that frozen checkout, not a later development checkout containing PR #15's different runtime bytes. Do not rewrite input hashes to make a newer runtime pass this historical observation. The retained runtime and manifests identify exactly what was measured.

OpenAI's [non-interactive CLI documentation](https://learn.chatgpt.com/docs/non-interactive-mode) was used through the OpenAI Docs skill to verify JSONL events, output-schema and controlled execution settings before launch. All requested model/effort settings remained gpt-5.6-sol/xhigh with the same 1200-second timeout in both arms.
