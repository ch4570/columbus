# Current-skill actual model usage observation

2026-09-08 KST. **This cohort did not demonstrate lower cumulative model input.** Six predeclared runs used gpt-5.6-sol, xhigh, Codex CLI 0.153.4, the unchanged historical source fixture, and the current frozen Columbus engine/skill. [Plan](PLAN.md); [complete evidence](controlled.json).

| Task | Baseline input | Skill input | Input change | Baseline / skill citation gate |
| --- | ---: | ---: | ---: | --- |
| Export safety | 50,863 | 79,914 | +57.12% | pass / pass |
| Configuration invalidation | 59,490 | 49,686 | −16.48% | fail / fail |
| Managed installation | 32,707 | 64,947 | +98.57% | pass / pass |

All six trials completed with actual `turn.completed.usage`, unchanged source, matching settings and valid frozen source/engine preflight. Nothing was selectively rerun or omitted. The configuration pair's lower input is not quality-qualified savings: both answers inserted literal ellipses into fields required to contain a verbatim quote. The grader was not relaxed. The four passing answers' explanations were also reviewed against the cited mechanisms; they correctly describe the directory guard, path equality guard, exclusive creation, conflict/hash checks and backup restoration.

All three skill trials read the frozen SKILL.md and then chose ordinary source search; **zero frozen graph-tool invocations occurred**. This evaluates the cost of loading current routing instructions on these small tasks, not the performance of active graph use. The first skill run emitted 63.24% fewer shell-output bytes but consumed 57.12% more cumulative input. More commands and skill-reading overhead are plausible contributors; this observational run does not isolate their causal effects. Cache variation and nondeterministic model behavior remain uncontrolled.

Cached input is already part of input. The export pair had fewer uncached tokens despite more total input; the managed-installation pair increased both. No billing claim is made. Startup/tool/skill context is included in actual usage. Requested model aliases are not provider-backend attestation. One run per condition on three questions is insufficient for general efficiency claims.

The harness now supports `freeze-engine --with-skill`: skill/reference files are hashed and protected by preflight, and the prompt does not force graph-first retrieval. Thirteen harness tests passed, including rejection of skill changes before any model invocation. Historical graph-first replay behavior remains available without the flag. Raw event transcripts and the frozen runtime/source are retained locally at `.omx/observations/current-skill-9913ce7/`; published records retain hashes, commands, prompts, final answers and usage while omitting reasoning transcripts and replacing local prefixes with `$RUN`, `$CHECKOUT` and `$PYTHON`.

[Official non-interactive documentation](https://learn.chatgpt.com/docs/non-interactive-mode) documents JSONL operation and runtime usage events. The measured numbers above come from the local runtime events, not byte estimates or documentation examples.

## Next iteration

Do not load a graph skill merely to answer a known literal/path lookup. Keep ordinary search as the cheap default and make graph-specific entrypoints discoverable when they are useful. A future graph-use study should predeclare genuinely relational or repeated-context tasks, enforce the same answer-quality gates, retain failures, and measure actual runtime usage. Do not redesign or selectively repeat this completed cohort to manufacture a reduction. The overall token-reduction goal is still unproven.
