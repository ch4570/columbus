# Four-arm workflow and tool observations

This is a new study, separate from the immutable RepoAtlas 0.4 [paired observations](README.md). It tests **availability and policy**, not compulsory tool use. All arms receive the same task, authority, output schema, efficient shell tools and acceptance criteria.

| Arm | Columbus available | Additional short policy |
| --- | --- | --- |
| A | No | No |
| B | No | Yes |
| C | Yes, optional | No |
| D | Yes, optional | Yes, identical to B |

The policy binds the task once, permits direct reads for known files, makes orientation/relations conditional, changes entry point after no progress, retains receipts only within one agent's context and stops when evidence is sufficient. Where supported, it requests a named snippet session with 8 queries, 24,000 stdout bytes and 2 no-progress attempts. This is a short operationalization of [the task contract](../../skills/columbus/SKILL.md#task-contract), not a test of loading every installed skill/reference.

## Fixed scope and success

[factorial_cases.py](factorial_cases.py) builds 230 synthetic source files without executing them. Three cases cover a known Python function with mixed CR/LF and Unicode separators, complete evidence for 25 declarations beyond one search page, and unresolved Java/Python dynamic dispatch. Two repeats across four arms yield 24 planned attempts. A rotating/reversed order is fixed before model calls. These are read-only navigation cases in one small synthetic corpus with distractors, **not** representative real-world editing, tests, large monorepos or a population-level economics benchmark.

Machine grading requires every requested finding, the correct file, a physical CR/LF range containing the required mechanism (at most 40 lines), its full exact quote preserving indentation/Unicode, exact requested structured facts, and honest completeness/limitation codes. A wrong function, a missing region or `complete=true` for unresolved runtime targets fails. Prose is not graded by arbitrary keyword matching: every machine-passing answer additionally needs a reviewed, answer-hash-bound prose verdict before summary counts it as successful or comparable.

## Reproduce a fresh cohort

Use Python 3.11+, this repository's existing parser dependencies, Git, `rg`, and an authenticated Codex CLI supporting the options in [factorial.py](factorial.py). Select a model available in the account; no model or price is a permanent default. Do not run trials through an environment that injects different additional instructions into different arms.

```sh
python evals/exploration/factorial.py --output /ABS/NEW_STUDY prepare \
  --model YOUR_MODEL --effort high --repeats 2 --timeout 180
python evals/exploration/factorial.py --output /ABS/NEW_STUDY run
python evals/exploration/factorial.py --output /ABS/NEW_STUDY summary
```

`prepare` does not call a model. It freezes source, engine, protocol sources, answer schema, case oracles, schedule, requested model/effort, CLI version and an index digest. Cold index creation/checkpointing is timed separately; the index uses checkpointed DELETE journaling for read-only sandbox access. C/D receive that warm index as an optional tool; A/B may not use it. Actual tool adoption is observed, not assumed. Nonempty WAL writes, changed index/source/protocol or changed CLI version block the next model call. Do not edit protocol files while a cohort is running.

**`run` consumes authenticated model usage.** Every attempt starts an independent ephemeral agent. User configuration and project-document loading are disabled; host skill discovery is explicitly skipped, and web/delegation are disabled. The CLI may still supply built-in startup instructions/tools; reported usage includes them, and the study does not claim to know their separate token counts. Source/index are outside the writable scratch directory. Tool arms may additionally write only their session directory. Each attempt receives a unique session name, with no cross-agent receipt reuse.

Provider prompt cache is observed, not cleared or guaranteed cold. Cache/load/order effects remain limitations. Missing shell tools or invalid commands count as actual failures and work, not successful zero-cost calls. No model trial runs in CI.

The no-argument `run` visits the predetermined schedule sequentially and skips already-started directories. It never overwrites or automatically retries an outcome. An explicitly chosen retry uses `run --slot N --attempt 2`; all prior attempts remain in the denominator's task group and the cost numerator. A partially captured attempt stays incomplete/unknown in summaries. A fresh cohort is required after protocol changes. Do not discard calibration, failed or superseded model calls from the overall research-cost accounting merely because they are outside a controlled comparison.

## Review, aggregate and retain

Read the answer and cited source, then write `prose-review.json` in the observation directory, keyed by `attempt_id`:

```json
{
  "CASE-REPEAT-ARM-a1": {
    "passed": true,
    "answer_sha256": "SHA256_OF_JSON_DUMPS_ANSWER_SORT_KEYS_TRUE_ENSURE_ASCII_FALSE_UTF8",
    "notes": "Concrete source-backed review, including possible contradictions and limits."
  }
}
```

The hash input is Python `json.dumps(answer, sort_keys=True, ensure_ascii=False).encode('utf-8')`. A missing verdict is unverified, not a quality pass. A reviewer cannot override a failed machine evidence gate merely by setting `passed=true`.

Regenerate `summary` after review. The summary revalidates source, capture inventories, original prompts, raw events, final answers and started attempt identities. It recomputes runtime usage and machine quality rather than trusting edited derived counters. Frozen protocol sources permit later inspection of exactly what ran. Hashes detect inconsistent local evidence, not a malicious filesystem owner who rewrites every digest and file together.

After the maintained harness changes, do not relax the old cohort's protocol guard. Reinspect it with its recorded runtime and `python /ABS/STUDY/protocol/factorial.py --output /ABS/STUDY summary`; use the current checkout for a fresh cohort. The published 2026-09-09 macOS observations precede the subsequent Windows LF/stdin and display-separator fixes. Their original protocol and outcomes remain preserved; those portability fixes did not rerun or rewrite the observations. New trials persist and send identical UTF-8/LF prompt bytes, independent of Windows text-pipe newline conversion.

Each arm reports all attempts, failures/retries/delegates, unique successful tasks, input/cached input/cache writes/output/reasoning details where reported, tool counts, exact duplicate shell commands, recorded output bytes and root wall time. Shell-command counts and CLI user-turn completion are **not internal model round trips**; that field remains unknown. Tool-output bytes are captured command stdout, not all protocol traffic or model input. Internal provider retries without separate usage reporting remain unobservable.

Same-quality blocks require all four arms to have a verified success and complete usage, including failed attempts in that task/arm. Token contrasts are signed deltas: B−A and D−C for policy; C−A and D−B for tool availability; D−C−B+A for interaction. Positive means more tokens, not an improvement. Failed/unverified blocks never contribute a savings percentage. Overall success and failure usage are still reported.

### Optional cost estimates

`summary --prices /PATH/prices.json` accepts an explicit OpenAI-only contract:

```json
{
  "provider": "openai",
  "model": "THE_OBSERVED_MODEL",
  "effective_date": "YYYY-MM-DD",
  "currency": "USD",
  "rates_per_million": {
    "ordinary_input": 0,
    "cache_read": 0,
    "cache_write": 0,
    "output": 0
  }
}
```

The zeros above are schema placeholders, **not prices**. Supply the applicable dated rates. Cached reads and cache writes are disjoint subsets of input; ordinary input is input minus both. Reasoning is already a subset of output and is never added again. CLI `cache_write_input_tokens` and `reasoning_output_tokens` aliases are normalized without treating an omitted field as zero.

Missing usage, model mismatch, unknown delegate scope, unknown pricing or unreported cache-write quantities leave monetary cost unknown. Only a separately justified `cache_write_accounting="included_in_ordinary_input"` price contract permits treating cache writes as having no separate charge. Parent and delegate usage is added only with explicit `usage_scope="self_only"`; ambiguous inclusive usage is not double-counted or assumed free.

`cost_per_successful_task` is **all attempt/delegate model cost divided by unique verified successful tasks in that arm**, including failed tasks and retries in the numerator. Zero successes is undefined. It is a supplied-rate model estimate, not a provider bill. Local indexing, other tool charges and engineering/reviewer effort are not silently folded into that amount. A separate exploratory elapsed-time amortization reports a reuse count only when observed warm-task wall-time savings are positive. It is not a dollar break-even point or statistical guarantee.

For private evidence retention, `pack --destination /ABS/NEW_ARCHIVE.zip` creates a reproducible archive only after a current summary is present. It preserves raw captures and frozen inputs, excludes scratch/git/cache data and never overwrites an archive. **Review logs for credentials, private data and reasoning traces before any public publication.** Public reports can instead retain structured measurements/answers and raw-event hashes while keeping original transcripts local.

`publish_factorial.py --output /ABS/STUDY --destination /ABS/NEW_REPORT.json [--pilot /ABS/PILOT]` publishes that restricted report with display-only path labels and no raw reasoning/stderr transcripts. It keeps all attempts and separates calibration overhead. If no Columbus command was observed, it suppresses any index-payback conclusion from the raw wall-time formula; unused indexes do not establish reuse savings.

Pilot summaries must match every started trial exactly, including failures and unfinished starts; a stale or duplicate inventory blocks publication. The controlled directory cannot also be passed as its own pilot, including aliases of the same directory. Runtime path labels are derived from captured origins as well as the current publication location. This is not a general private-data scrubber: inspect free-text answers and commands before sharing. These publication checks and the clarified index-availability metadata were added after the 2026-09-09 observations; the recorded cohorts and public measurements remain unchanged.

## Model-free checks

```sh
python -m unittest discover -s evals/exploration -p 'test_*.py' -v
```

The tests cover all four arms, frozen artifacts, raw/derived result mismatches, malformed/truncated events, failed launches, incomplete attempts, duplicate IDs, cache/reasoning overlap, retries, delegate scope, Unicode mis-citation, missing candidates and partialness overclaims. The [Korean study report](../../docs/workflow-cost.md) records actual observations and their limitations separately from harness correctness.
