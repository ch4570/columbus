# Read-only agent exploration observations

This harness compares ordinary `rg` plus bounded source reads with the same tools plus a prebuilt Columbus index. It runs real, independently started Codex CLI sessions. It never assumes that fewer response bytes mean fewer model tokens.

The [Korean report](../../docs/token-efficiency.md) explains the findings. The 2026-09-07 cohort contains all six controlled trials, including regressions and citation failures. The one pair passing both citation checks used **34.0% more cumulative input tokens** with RepoAtlas. No general token or billing savings were established.

The [current-skill cohort](results/current-skill/REPORT.md) adds six real runs with the current frozen skill and engine. Both quality-passing pairs increased cumulative input; the skill chose ordinary search in all three cases. It does not demonstrate graph-token savings.

## Recorded artifacts

| File | Purpose |
| --- | --- |
| [cases.json](cases.json) | Three fixed source-navigation questions and expected mechanism markers |
| [answer.schema.json](answer.schema.json) | Required answer structure |
| [Source fixture](fixtures/repoatlas-source-v0.3.0.zip) | Real 0.3.0 source bundle, with no unrelated padding |
| [Observed engine](fixtures/repoatlas-engine-observed-0.4.0.zip) | Exact 0.4.0 engine used in the model trials, before the later long-function excerpt fix |
| [controlled.json](results/2026-09-07/controlled.json) | Six trials, settings, prompts, commands, answers, usage, quality checks and file hashes |
| [excluded-preflight.json](results/2026-09-07/excluded-preflight.json) | Entire initial five-trial cohort excluded after discovery produced an empty index |
| [delivery.json](results/2026-09-07/delivery.json) | Model-free CLI output and receipt measurements on the current polyglot example |

The engine ZIP is immutable experimental evidence, not another maintained engine implementation. Production code lives under `skills/columbus/scripts/columbus/`. Archived fixtures, source-case paths and their hashes keep the original RepoAtlas names. They are historical inputs, not current installation instructions. Raw event transcripts stay in local `.omx/observations/`; published records include their hashes and omit reasoning transcripts. Local absolute paths are replaced with `$PYTHON`, `$RUN`, `$CHECKOUT`, or `$EXCLUDED_RUN` in published metadata. They are labels, not directly executable commands.

## Run a new comparison

Use Python 3.11+, the repository's parser dependencies, Git, ripgrep, and an authenticated Codex CLI supporting `exec --ignore-user-config --ephemeral --json --output-schema`. Preparing, freezing and summarizing do not call a model. **Each `run` command consumes actual model usage.** The model must be available in your account; choose it explicitly and keep the same model and effort for both conditions.

From this checkout:

```sh
python evals/exploration/observe.py --output .omx/observations/new-run prepare
python evals/exploration/observe.py --output .omx/observations/new-run freeze-engine
python evals/exploration/observe.py --output .omx/observations/new-run run \
  --case export-safety --condition baseline --model YOUR_MODEL --effort xhigh
python evals/exploration/observe.py --output .omx/observations/new-run run \
  --case export-safety --condition columbus --model YOUR_MODEL --effort xhigh
python evals/exploration/observe.py --output .omx/observations/new-run summary
```

For a new evaluation of the current skill’s actual routing, add `--with-skill` to `freeze-engine`. This freezes SKILL.md and its references, includes their hashes in preflight, and asks the enhanced condition to follow that skill rather than forcing graph-first retrieval. Archived engines cannot be combined with the current skill. The default retains the historical graph-first protocol for reproducibility.

Also run `configuration-invalidation` in Columbus → baseline order and `managed-installation` in baseline → Columbus order. A fresh trial uses `--repeat 2`, then `3`, in **both** conditions; predeclare the number of repeats. Do not rerun only unfavorable answers or overwrite earlier evidence. The harness refuses an existing trial directory. The default freeze uses current Columbus production code against the fixed source fixture and creates a new cohort. To replay the recorded tool, freeze with `--engine-fixture evals/exploration/fixtures/repoatlas-engine-observed-0.4.0.zip` in a fresh directory and use the `repoatlas` condition. A condition must match its frozen engine. Current runs use `.columbus/index-v1.sqlite`; archived replays use the recorded `.repoatlas/jvm-v2.sqlite`. Never rename or overwrite published observation inputs to fit a new brand.

The preserved RepoAtlas 0.4 engine cannot replay on **Windows with Python 3.14** because its original `stat`/`fstat` handling mistakes creation/change timestamps for a concurrent edit. The harness refuses that exact archived input before copying or executing it; use Windows/Python 3.11, Linux, or macOS for this replay. CI skips only the archived execution test on that known incompatible combination. Archive checksums and file inventory, the compatibility guard, and current Columbus engine tests still run there. The archive and historical observations remain unchanged; a skipped replay is not a successful historical execution.

Preparation extracts the source snapshot, initializes its own Git root and verifies the case markers. Freezing copies one engine and creates a nonempty index. Trials verify the case catalog, source manifest and engine manifest before running. Snapshot source must remain unchanged. Model sessions use a read-only sandbox, with web and delegation disabled; repository code, tests and builds are forbidden in the task. The graph tool itself is permitted only in its enhanced condition.

The model receives a useful ordinary-search baseline. In the default protocol the enhanced condition is instructed to start with the frozen tool’s search or context query and may fall back to shell reads. Thus the experiment evaluates that specific routing strategy, not every possible agent policy. The installed global skill catalog still appeared in both conditions despite ignoring user configuration; startup context and the longer enhanced prompt are included in measured usage. Caches are not reset. Identical settings cannot make independent model executions deterministic.

## Measures and quality gate

- Read actual token usage from the final `turn.completed.usage`. Missing usage stays missing, never zero.
- `cached_input_tokens` is a subset of `input_tokens`. Derive uncached input by subtraction; do not add the cache again. Do not add reasoning tokens to reported output again.
- Count completed shell command items and UTF-8 bytes of their recorded `aggregated_output`. This is neither total tool-protocol bytes nor model round trips.
- Keep wall time and cold index work separate. A prebuilt index is an explicit advantage whose cost is recorded.
- Require matching nonempty requested model/effort, a nonempty index, unchanged source, clean completion and no unexpected tool types before a pair is comparable.
- Check each answer's requested ID, file, real source range of at most 40 lines, expected mechanism, contiguous quote and nonempty explanation. Ignore code-line indentation. An ellipsis is not a verbatim quotation. Review explanation semantics separately.
- Only pairs passing **both** citation checks may support an equal-quality savings comparison. Preserve all other rows, their failed checks and initial grading results.

The initial empty-index cohort is excluded in full, including its baselines. Source-directory isolation, a nonempty preflight and a product discovery regression fix preceded the fresh six-trial cohort. Grader v2 was uniformly applied to all recorded answers after allowing harmless indentation differences; the original grades remain available. Two baseline answers still failed due to three noncontiguous quotations. Their mechanisms were largely correct; citation failure alone is not proof of semantic misunderstanding.

One real repository, three read-only questions and one execution per condition cannot establish a population effect. Do not derive billing savings, confidence intervals, broad accuracy improvement, or long-running coding performance from this sample. The subsequent agent-routing guidance and long-function excerpt fix have regression evidence, but no new model A/B claim.

## Local checks without model calls

```sh
python -m unittest discover -s evals/exploration -p 'test_*.py' -v
python scripts/observe_delivery.py
```

CI runs these deterministic checks and never launches the model trials. The separate `scripts/benchmark_context.py` remains a synthetic whole-source-versus-response illustration; it is not the baseline used here.

## Archive evidence for future cohorts

[archive_evidence.py](archive_evidence.py) provides the opt-in `archive-evidence-v1` recognizer for new collectors:

```python
from archive_evidence import graph_evidence
receipts = graph_evidence(events, observation_directory, task_evidence_paths)
```

It recognizes successful commands against the frozen runtime/archive and validates JSON, legacy source text and current file/declaration-table text. Receipts report operation, encoding, output hash, task-path relevance and batch use without retaining source or conversation text. Empty, failed, malformed or merely offered commands do not establish useful graph evidence. Recognition is not an answer-quality grade or an independent source/hash verification gate.

Before any new model run, freeze/hash this module, its tests and the new collector alongside the source, archive, runtime, skill, task catalog and full quality rubric. Record `recognizer_version` in results; keep actual input/output, citation and semantic checks separate. Historical collectors and frozen cohorts deliberately retain their original recognizers and acceptance criteria. These parser tests neither rerun nor upgrade prior failed results.

Custom predeclared tasks can now be prepared with `prepare --fixture SOURCE.zip --cases CATALOG.json`. The catalog is copied into the observation directory and hash-checked at execution and summary time; later edits to the external catalog cannot rewrite prepared tasks. Historical observations without a frozen catalog retain their original hash validation. IDs and evidence paths are validated. The new [relational pilot plan](results/relational-pilot/PLAN.md) has a prepared current-source fixture but no model measurements yet.
