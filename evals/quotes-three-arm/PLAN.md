# Prospective three-arm quote-extraction cohort

No model has run when this plan is written. Freeze all inputs and pass source, citation, relationship and harness controls before any launch. This is a new experiment, not a regrading or retry of the previous failed cohorts. The current historical input/output and full-quality failures remain failures. PR #12 to main and any release remain gated.

## Question and comparison

Measure complete exploration with ordinary source tools (baseline), Columbus immediately before PR #17 (control, commit `9c0d3c3a54022237d32b9790ba4c1e0b2a758124`), and Columbus including PR #17 (quotes, commit `402940994ba519a3a02a521ccfed55b73d310dbf`). The latter two differ in the quote command, associated CLI hardening and usage guidance. They are not literally the same executable with one feature flag. Freeze the exact runtime/skill/reference exports from each commit. Do not mix current skill prose with the control runtime.

Primary: baseline versus quotes in each of six task/repetition pairs. Secondary: control versus quotes, estimating this package change's contribution within Columbus. A secondary improvement cannot substitute for the primary gate. A missing or failed control run is retained and makes the complete three-arm experiment incomplete, even if a primary pair succeeds. Report all 18 executions and both comparisons.

Three new operations on previously used pinned corpora: Java concurrent cache lifecycle, Kotlin-to-Java proxy hint registration, and JavaScript download/sendFile transfer/error routing. These are not held-out repositories. Java/Kotlin use the complete frozen Spring `spring-core` subtree, not the complete Spring Framework repository; Express uses its full pinned superproject ZIP, without vendored dependencies. The source ZIPs are canonical byte corpora, identical across all arms. Do not silently expand their scope or execute upstream code. Source reviews state implementation and dependency boundaries.

The Spring repository-root Apache license is retained separately as `LICENSE.spring-framework.txt` from the same pin. It is not added to or claimed to be inside the unchanged subtree source ZIP. Express's license is already in its canonical ZIP.

## Full navigation, not supplied excerpts

The shared task prompt requests finding discovery, entry/helper relationships, all stated behaviors and edge cases, and representative source citations. It does not reveal grader paths/ranges/markers or relationship controls. Every clause is source-reviewed and explicitly requested in the task question/finding descriptions before launch. One representative quote per finding need not encompass every cross-file explanatory clause. Each quote is contiguous, within a correct range of at most 40 physical source lines; indentation is ignored by the unchanged citation grader. Incorrect/extra/missing findings or contradictory prose fail. All source-reviewed clauses remain mandatory; there is no partial-quality acceptance.

All arms may use efficient ordinary search, multi-range batched reads and standard-library source-to-JSON extraction. None is forced to dump whole files. Columbus arms read their own skill and may choose ordinary tools. The quote command is optional; adoption and non-adoption are measured, never repaired by rerunning or forcing a quote-only subtask. Runtime hashes and exact excerpts alone do not prove useful graph relationships or semantic correctness.

Private criteria, controls and prior results are outside model repositories. Prompts restrict inspection to the repository and explicitly offered runtime/skill/reference/archive; no sibling experiments, private harness or oracle files. Read-only sandbox is defense in depth, not a claim of inaccessible host files. Independently review every command trace for compliance. Authentication/provider requests are not model web research.

## Fixed execution and preservation

Exactly three tasks × two repetitions × three arms = 18 executions. Each language's six executions are sequential; language groups may run concurrently. The six orders use every permutation once, balancing position and directional adjacent carryover across the cohort:

| Task | Repetition 1 | Repetition 2 |
| --- | --- | --- |
| Java | baseline → control → quotes | quotes → control → baseline |
| Kotlin | control → quotes → baseline | baseline → quotes → control |
| JavaScript | quotes → baseline → control | control → baseline → quotes |

Keep requested model `gpt-5.6-sol`, effort `xhigh`, timeout 1200 seconds, local Codex CLI 0.153.4, read-only sandbox, no upstream execution, no web/delegation, structured final JSON schema. The model alias is a requested setting, not backend attestation. JSONL `turn.completed.usage` supplies actual total input/output; cached input and reasoning are subsets, never added again. No pricing inference from CLI authentication. Verified with the OpenAI Docs skill against [official non-interactive documentation](https://learn.chatgpt.com/docs/non-interactive-mode) and [model settings](https://developers.openai.com/api/docs/models/gpt-5.6-sol).

Preparation records environment and cold index/export work separately. Every arm receives a byte-identical saved graph and source corpus for its task; no consumer SQLite remains. Graphs are produced once with the quotes runtime; non-CLI analyzer bytes must match the control runtime, and both arms' graph controls must pass. Baseline does not receive graph/runtime instructions or permission to use them. It is still subject to the same source/archive integrity checks.

Before launch, freeze this plan, source/criteria/reviews, controls, prompts' construction, schema, runner, collector, recognizers, tests, exact runtime/skill/reference files and source/archive/observation manifests. Commit and push the frozen protocol before the first model process. Verify the frozen inventory and all three arms' source/runtime/archive integrity before and after every model invocation. Preserve original prompts, argv, process identity, terminal time/status, raw events/stderr, answer and result hashes. Keep terminal process status even if parsing fails later. Do not infer process termination from an absent result. No overwriting existing trials, selective retries, extra repetitions, source substitutions, prompt/rubric changes or failure exclusions after launch.

## Acceptance and independent review

Each accepted run needs exactly one successful completed turn, valid actual usage, matching frozen prompt/argv/settings/schema and unchanged inputs, full citation correctness, and independent semantic review of every numbered clause bound to answer SHA and frozen source-review SHA. An independent execution review binds raw event SHA and checks every command. Missing reviews are pending, never passes. Unexpected tools, terminal errors, timeouts, malformed output or extra findings fail.

Graph utility is stricter than historical retrieval receipts: a successful frozen-runtime/archive callers/neighbors response must deliver at least one prospectively source-reviewed exact relationship, with matching source hashes. Search results, declarations, source-only packets and quotes alone do not count. Preserve narrower graph omissions instead of inventing edges. Both Columbus arms require this utility condition for the complete experiment. Separately recognize successful source-matching quote packets; recognition does not imply citation/semantic approval.

In EVERY primary pair, quotes must have strictly lower total `input_tokens` AND strictly lower `output_tokens` than baseline, with both arms passing full quality and protocol, and quotes passing graph utility. Equal/increased or missing tokens fail. All six primary pairs and all 18 valid full-quality runs are necessary for complete experiment acceptance. No averaging or cross-pair compensation. Secondary control/quotes results are reported with their own full-quality and utility checks; their failures or regressions must be explicit. Complete acceptance is neither universal savings proof nor automatic release authority; main/release also needs the final exact-head functional/distribution/platform gates.

Historical collectors/manifests remain unchanged. A frozen experiment must be reproduced at its original inputs, not by rewriting old hashes to accommodate later development.
