# Live continuation and usage-semantics preflight

On local `codex-cli 0.153.4`, a new persistent session using requested `gpt-5.6-sol` / xhigh was asked to remember `cedar-7362-river` and answer READY without tools. Its exact recorded UUID was then passed to `codex exec resume`; the second prompt asked for the earlier token without repeating it. The answer was exactly `cedar-7362-river`. Both JSONL captures passed thread-continuity/event-order validation. No tools were used by either model turn.

| Counter | First completion | Resumed completion | Second-turn delta |
| --- | ---: | ---: | ---: |
| Input | 9,153 | 18,336 | 9,183 |
| Cached input subset | 0 | 8,960 | 8,960 |
| Output | 5 | 16 | 11 |

The persisted rollout's `total_token_usage` equals each CLI completion's usage. Its second `last_token_usage` equals the adjacent difference, establishing **cumulative** completion reporting in this runtime. Summing both completions would incorrectly report 27,489 input tokens instead of 18,336. The [filtered token-count records](token-counts.json) and [audited captures/deltas](audit.json) preserve this evidence without publishing reasoning traces. Raw captures, stderr and the exact resume command remain in `.omx/observations/resume-preflight/`.

The auditor now offers `--usage-mode cumulative`, which computes adjacent deltas and uses the last cumulative report as the total, rejecting decreasing or impossible counters. Default mode still leaves aggregation unproven. Use cumulative mode only with independently established runtime semantics and captures beginning with a genuinely new thread; do not assume other clients or future versions behave identically.

Three tests cover continuity rejection and cumulative-delta arithmetic. This live smoke test proves short conversation continuity and observed counter semantics. It does not prove retained source through compaction, receipt use by an agent, code-answer quality, or any token-saving benefit. The full continuous-work comparison remains outstanding.
