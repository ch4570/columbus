# Persistent two-turn receipt source-navigation pilot

Both conditions pass all four exact-citation/mechanism checks, but Columbus increases cumulative input **131.66%**. This pilot does not demonstrate actual-token savings.

[Predeclared plan](../PLAN.md), [auditable results and original prompts](controlled.json), [verified cumulative-counter semantics](../resume-preflight/README.md). Executed 2026-09-08 with Codex CLI 0.153.4, requested gpt-5.6-sol/xhigh, baseline then Columbus, two turns each. These are requested runtime settings, not backend model attestations. Each condition starts a new persistent session and resumes its exact UUID. Frozen c67b20a source and the engine/skill manifests are included. All four source/engine/index immutability checks pass.

| Runtime counter | Baseline | Columbus | Change |
| --- | ---: | ---: | ---: |
| input_tokens | 43,594 | 100,991 | +131.66% |
| cached_input_tokens | 28,416 | 66,688 | +134.68% |
| uncached_input_tokens | 15,178 | 34,303 | +126.00% |
| output_tokens | 1,538 | 2,355 | +53.12% |

Counts use the last cumulative report, not the sum of both reports. Second-turn input deltas are 12,402 and 17,044 respectively. Cached-input differences are observations, not controlled cache conditions or dollar-cost estimates. Elapsed totals are 61.01s and 93.59s.

Baseline used two commands (search and a full 125-line receipt-file read). Columbus used six: skill read, failed search, search help, corrected search, context reference read, and one successful receipt-backed context request. The context packet delivered receipt and CLI source and created a two-file receipt. **Neither condition invoked tools on turn two.** Both naturally reused retained source; no repeated retrieval occurred, so receipt-specific suppression was not exercised.

The original prompt ambiguously put `--snapshot` alongside the global repository option. Columbus first placed it before the subcommand (exit 2), then corrected it using help. This is a harness/routing confound, not a clean estimate of intrinsic graph overhead. The failure is retained in the totals; there was no selective retry. Future runner prompts now explicitly place `--snapshot` after the subcommand; that correction was not used for this observation.

Manual source review confirms new-receipt initialization, repository ownership rejection, two-hash span compatibility, and the pre-write existing-file check. The last check is not an atomic multiwriter compare-and-swap guarantee; answer wording about preventing intervening modifications must be read within that limited check.

One short scenario, one execution per condition, unchanged source, fixed order, and no compaction stress do not establish general performance or long-session retention. Previous negative caller pilots remain valid observations. Raw captures, stderr, frozen source/runtime and scratch receipt are retained locally under `.omx/observations/continuous-pilot`; tracked results include capture hashes, commands, answers, prompts, invocation settings and cumulative/delta counts, excluding raw reasoning. The overall actual-token goal remains unachieved.
