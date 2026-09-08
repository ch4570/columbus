# Source/call-site packet: prospective three-arm cohort

Status: preparation only. No model has been launched for this cohort. This file,
the task/rubric/source reviews, relationships, controls, runtime exports and every
used harness dependency must be frozen and committed/pushed before execution.
Preparation results, including any rejected control, are reported separately.

## Question and scope

Does optional `archive-source --call-sites` plus its saved-graph guidance reduce
actual total input **and** actual total output while retaining complete code
navigation answers, exact citations, valid execution and useful graph delivery?

Use three conditions: efficient ordinary shell exploration (`baseline`), Columbus
at commit `402940994ba519a3a02a521ccfed55b73d310dbf` (`control`), and Columbus at
commit `382d92a780e933f43e267d12f41869c816eee3bb` (`candidate`). The latter is the
exact tested PR #21 head, including the unchanged PR #18 evidence tree. Export
only each committed runtime/skill/reference package. Verify the package delta
before preparation; neither arm is an editable development installation.

The candidate feature returns source and every stored calls edge on the returned
physical lines, including nested owners and duplicates. It is not a complete
runtime call graph, nor proof that arbitrary receiver dispatch is resolved.
Unresolved reference counts and archive-only endpoints are not resolved edges or
current-file verification. Existing unflagged commands remain available.

Tasks cover Java resource-location resolution, Kotlin property access through
ordered property sources, and JavaScript Axios URI construction without dispatch.
Exact upstream commits, complete archived corpus boundaries, findings, semantic
clauses and independently reviewed relationships live in the per-language files.
The repositories and some operations are reused, not held out. Java overlaps the
historical `evals/spring-navigation/cases.json` resource-loader task; Kotlin adds
an extension entry point to property-resolution mechanisms already exercised in
`evals/multilang-token-batch/java/cases.json`. This is a fresh matched comparison
of the new package, not a new-operation benchmark or a retry/replacement of those
historical observations. Tasks were selected after inspecting source and available
edges, so this is explicitly an edge-informed development evaluation, not an
unbiased benchmark or evidence of broad generalization. Kotlin extension dispatch
limitations remain visible, and a useful saved Java helper edge must not be
misrepresented as a resolved Kotlin-to-Java handoff.

## Fixed schedule and execution

One task per language, all three arms, two repetitions: exactly 18 executions.
Across the six language/repetition blocks use all six arm permutations once:

| Language | Repeat 1 | Repeat 2 |
| --- | --- | --- |
| Java | baseline, control, candidate | candidate, control, baseline |
| Kotlin | control, candidate, baseline | baseline, candidate, control |
| JavaScript | candidate, baseline, control | control, baseline, candidate |

Each language runner executes its six slots sequentially. Different language
runners may operate concurrently. No selective rerun, retry, resume, resampling,
early success selection, answer editing or post-result rubric change is allowed.
Preserve unsuccessful commands, timeout/termination receipts and every started
execution, including one that lacks a completed-turn usage record.

Request `gpt-5.6-sol`, reasoning effort `xhigh`, a 1,200-second timeout, the same
JSON answer schema and frozen CLI configuration for all arms. Requested model and
effort are configuration, not backend attestations. Preserve raw JSONL events,
exact prompts/argv, process and terminal records, stderr, raw final answer and
parsed metrics. Read-only execution uses saved authentication without inspecting
or copying credentials. No repository code/tests/builds, network, delegation,
installation, index synchronization, private harness/oracle access or source
writes are allowed. All arms may use efficient batched search and bounded source
reads, including standard-library scripts producing exact JSON excerpts. Skill
and command choice remain optional within the graph arms; adoption is measured,
not forced. No unseen oracle paths, IDs or relationship tuples enter prompts.

This new cohort explicitly adds `--ignore-rules` to the prior read-only CLI
isolation and binds the resolved Codex executable path/hash as well as its version.
The change applies equally to all new arms and never alters earlier invocations.

## Freeze, controls and independent review

Prepare fresh source/runtime copies and a saved graph outside the source tree;
verify every arm has identical source bytes and identical graph bytes. Reuse the
byte-identical historical graphs bound in `graph-bindings.json`, after validating
their producer/source/analyzer provenance as described in `GRAPH-REUSE.md`.
Do not build a new index or export. Keep original producer identity and historical
timings; new cold index/export fields are null, not fabricated zero measurements.
Measure new copy/verification time separately, remove only newly created Git
metadata, and prohibit consumer SQLite. Bind source ZIPs, licenses, provenance, file hashes,
graph revision/counts, package bytes, Python/package/CLI environment, schedule,
all questions/clauses, reviewed relationships, command grammar and all harness
dependencies. Preparation requires at least 384 MiB free: a 128 MiB allocation
allowance above the unchanged 256 MiB post-preparation/freeze/launch reserve.
The pinned source/runtime/ZIP/graph files alone estimate 106.15 MiB at 4 KiB
rounding; directories and preparation receipts need additional space. No failed
preparation or control capture is silently restarted.

Prelaunch controls use actual tool invocations in both JSON and text where
supported, complete citations, and predeclared relationship tuples. For the new
source/call mode, verify output against independently reconstructed
source/page/edge/endpoint/reference data. Legacy neighbor/caller/quote recognition
is unchanged; do not generalize the new mode's exact replay guarantees to it.
Include failed-command, wrong tuple, tampered output, omitted/duplicated edge,
incorrect source/cursor/hash, unrelated valid packet and quote-only negatives.
Both graph arms now support archive-quotes; only the candidate supports the new
call-sites flag. Controls are model-free delivery tests, never model outcomes.
Reproduce captured controls before each model execution and during collection.

Reserve a control attempt marker before any process starts. Retain raw output
bytes and launch/timeout/decode failures before validation; failed captures cannot
be overwritten or silently repeated. The new cohort adapter reads binding values
from observation receipts, and must therefore be used inside the collector's
authoritative frozen-input and pre/postflight checks, not as a standalone attester.

Review every final answer against every frozen clause with explicit pass/fail
reasons and exact answer/rubric hashes. Review all commands against the frozen
execution rules and bind that review to raw events. Tool-delivery receipts do not
replace semantic understanding or citations. Unknown or missing review is pending,
not a pass. An unrecognized shell syntax receives no machine delivery credit;
that alone is not a protocol violation. Altered frozen inputs fail cohort
verification, rather than becoming negative evidence about a model.

## Acceptance: unchanged strict totals

For each of the six primary candidate-minus-baseline pairs, both executions must
pass terminal/execution, exact citation and **all** semantic requirements. The
candidate must actually receive a pre-reviewed useful saved relationship. Its
actual total `input_tokens` **and** actual total `output_tokens` must each be
strictly lower than its matched baseline. Equality, missing usage, any failed
quality obligation or missing utility rejects that pair.

Report all six secondary candidate-minus-control comparisons separately with the
same two strict inequalities and full quality/utility for both graph arms. They
cannot substitute for failed primary comparisons. Overall acceptance requires
all six primary pairs, all 18 full-quality executions, graph utility in every
graph-arm execution, all frozen inventories and every schedule check to pass.
Do not average away failures or use cached-input-only gains, byte counts, command
counts, assumed prices or inferred billing as actual token savings. Cached input
and reasoning output are subsets, not additive totals.

Earlier 12-run and 18-run failures remain immutable and separately reported. This
cohort does not regrade them. Retain complete raw evidence and reviews before
merging evaluation results. Development PRs may merge only after exact-head native
CI and tested/merged tree verification; PR #12 targeting main, tags and releases
remain on hold.
