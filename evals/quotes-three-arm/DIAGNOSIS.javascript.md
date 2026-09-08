# JavaScript: completed three-arm diagnosis

Neither JavaScript primary pair passes: the quotes arm uses more total input and output tokens than baseline in both repetitions. Neither secondary pair passes either. The first has lower token totals but a control citation failure; the second has both a control citation failure and higher quotes-arm input. Smaller final answers, cache subsets, or averages do not replace these per-pair conditions.

This supplemental diagnosis covers only the six completed `javascript-express-download-transfer` trials. It does not change the frozen experiment, repair an answer, regrade a semantic review, retry a model, or assess any subsequent implementation.

## Evidence and measurement

The source is the frozen Express snapshot associated with commit `023767fe9872e029271df1418f73401bff20ff40`; scope and provenance limitations remain those in [SOURCE-REVIEW.md](javascript/SOURCE-REVIEW.md). Baseline was offered ordinary repository tools, not Columbus. The control runtime is `9c0d3c3a54022237d32b9790ba4c1e0b2a758124`; quotes uses `402940994ba519a3a02a521ccfed55b73d310dbf`. This is a reused repository with a new operation, not held-out-repository evidence.

Read-only recomputation used the frozen harness in `/tmp/columbus-quotes-cohort.Qk2TI0/evals/quotes-three-arm` and raw observations under `/private/tmp/columbus-three-arm-observations.DJ4jA2/observations/javascript`. For arm `A` and repetition `R`, the trial directory is `A/trials/javascript-express-download-transfer-A-R/`.

- Each run has exactly one actual `turn.completed` usage record. Its fields, including cached input, agree with `result.json`; uncached input is total input minus cached input. No usage is estimated from bytes. Cache-write input is zero in all six runs.
- Completed command records were recomputed with the frozen `OBSERVE.parse_events`: command counts, failures, UTF-8 `aggregated_output` bytes and output hashes agree with the results. Each receipt is counted once, not once per started/completed event. Output-token totals are the reported full totals, not final-answer-only counts. Internal reasoning contents were not inspected.
- `common.verify_observation` passed before and after inspection for all three arms: 213 source files verified, 211 indexed files, matching runtime manifests and archive, and no consumer index. JavaScript `verify_order` passed, including process slots and the original runner terminal record.
- `collect_trial` validated terminal records, prompts/invocations, raw-event/result parity, answer equality with the final message, and the unchanged machine citation grades. All six existing semantic reviews passed their exact six-ID/23-clause checks. Their `answer_sha256`, `rubric_sha256` and execution `events_sha256` bindings match the raw files; no review was edited.

`B`, `C`, and `Q` below mean baseline, control, and quotes; the numeral is the repetition.

| Run | Total input | Cached input subset | Uncached input | Total output | Commands | Tool-output bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B1 | 66,092 | 31,360 | 34,732 | 7,072 | 5 | 17,991 |
| C1 | 152,864 | 115,968 | 36,896 | 13,832 | 10 | 34,664 |
| Q1 | 89,677 | 61,184 | 28,493 | 11,071 | 10 | 50,653 |
| B2 | 40,488 | 23,296 | 17,192 | 9,375 | 4 | 22,510 |
| C2 | 106,934 | 86,016 | 20,918 | 13,214 | 7 | 32,935 |
| Q2 | 115,356 | 77,184 | 38,172 | 12,185 | 9 | 37,935 |

Final-answer sizes are actual UTF-8 bytes. Each final file equals its compact, non-ASCII-escaping JSON serialization. Quote/explanation columns give summed decoded string bytes followed by their JSON string-value bytes, including quotes and escaping. The remaining keys, IDs, paths, coordinates and punctuation occupy 651 bytes in every answer, so each final JSON size equals its two JSON-value sums plus 651.

| Run | Final JSON bytes | Quote bytes: decoded / JSON | Explanation bytes: decoded / JSON |
| --- | ---: | ---: | ---: |
| B1 | 11,105 | 3,393 / 3,540 | 6,902 / 6,914 |
| C1 | 11,458 | 3,313 / 3,454 | 7,341 / 7,353 |
| Q1 | 10,399 | 3,396 / 3,544 | 6,192 / 6,204 |
| B2 | 10,732 | 3,393 / 3,540 | 6,529 / 6,541 |
| C2 | 11,049 | 2,670 / 2,785 | 7,601 / 7,613 |
| Q2 | 10,640 | 3,385 / 3,533 | 6,444 / 6,456 |

## Quality and separate pair decisions

All six runs pass terminal/execution review and all 23 semantic clauses. Baseline and quotes pass all six citation checks in both repetitions. Both controls fail only the `finish_race` citation check: C1 declares 959–979 but quotes 959–980; C2 declares 964–979 but quotes 964–980. Those incorrect endpoints remain unchanged. Semantic support does not waive citation correctness.

The frozen pair gate requires full quality on both sides, a recognized reviewed relationship for graph arms, and strictly lower quotes-arm total input **and** output. Deltas below are quotes minus the named comparator; percentages use that comparator's total.

| Comparison | Input delta | Output delta | Frozen pair decision |
| --- | ---: | ---: | --- |
| Primary Q1 vs B1 | +23,585 (+35.69%) | +3,999 (+56.55%) | Fail: both token conditions |
| Primary Q2 vs B2 | +74,868 (+184.91%) | +2,810 (+29.97%) | Fail: both token conditions |
| Secondary Q1 vs C1 | −63,187 (−41.34%) | −2,761 (−19.96%) | Fail: control citation |
| Secondary Q2 vs C2 | +8,422 (+7.88%) | −1,029 (−7.79%) | Fail: control citation and input condition |

For example, Q1 has 6,239 fewer uncached input tokens than B1, but this does not change its higher total input and output. Q2 does not repeat even that subset reduction. No averaging or favorable secondary comparison compensates for a failed primary pair.

## Observed work and useful delivery

The baselines use only ordinary discovery and bounded source reads: five commands in B1 and four in B2. All graph arms add a skill read, declaration searches, a batched declaration-source response, and two incoming-call probes. Those are observed workflow differences, not allocations of token cost to particular operations.

- C1 additionally makes an ambiguous shorthand `archive-source` call (`item_7`, exit 2, 117 output bytes), then searches `download` (`item_8`, 738 bytes) and recovers with exact IDs. This is a permitted lookup failure, not an execution-policy violation. C2 avoids that failure but its skill-read command also lists the offered runtime files, producing 9,489 bytes in total.
- Q1's ordinary discovery/read commands produce 26,165 bytes, including a 4,110-byte file listing, a 13,308-byte search and an 8,747-byte source read. Its final excerpts were already present in that source read and in the subsequent declaration packet. C1 likewise returns ordinary source and then declaration source containing its final excerpts.
- Each successful batched `archive-source` response in C1, C2, Q1 and Q2 is 6,083 bytes and contains 182 distinct numbered physical source lines for the three declarations. C2 additionally rereads imports and the helper with `sed`; Q2 performs no separate ordinary source read after discovery.
- Q1 and Q2 then request six exact ranges in one `archive-quotes` command, adding respectively 4,870 and 4,859 output bytes. The frozen recognizer validates both receipts, and all six final path/start/end/quote tuples in each answer equal the respective delivered tuples exactly. This establishes adoption, not understanding, causal error prevention, or a token saving. Both baselines also produce correct citations without this operation.

The frozen `quotes-three-arm-evidence-v1` recognizer was rerun against all four pre-reviewed [relationships](javascript/relationships.json), with source/runtime/archive preflight verified. Every graph arm delivers the same relevant stored edge, `lib/response.js::sendFile:function` → `lib/response.js::sendfile:function` at line 406: C1 `item_4`, C2 `item_5`, Q1 `item_8`, Q2 `item_7`. This supplies a genuine saved direct-call relationship alongside source evidence; it is not inferred merely from similar names or quoted code. None of these runs receives a recognized receipt for the three reviewed nested `onfinish` relationships. Every graph arm's other probe, for incoming public `sendFile` calls, returns zero edges and is not credited as positive relationship evidence. Baseline has neither relationship nor quote-extraction receipts, as expected for its allowed tools.

The archive reports 10,946 unresolved references out of 11,251 repository references; these are not a count of missing calls in this particular mechanism. The graph is heuristic and semantically incomplete. In particular, absence of the dynamic `download` → `this.sendFile` edge does not establish absence of that source-level handoff. Delivery receipts also do not prove that the model relied on or understood the delivered relationship; the semantic reviews remain separate.

## Prospective design motivation, not a tested intervention

There is a concrete evidence-reuse opportunity: the public-to-private call site is already inside requested declaration source, yet graph arms retrieve a separate caller response to obtain the stored relationship. A general-purpose opt-in `archive-source --call-sites` could attach all stored call sites whose physical lines lie in the delivered source page, retaining actual nested-owner and target IDs, hashes, fidelity and uncertainty. Shared file/endpoint tables could avoid repeating the same source as call context. This would be calls **in the excerpt**, not an exhaustive traversal of all calls owned by a selected class or declaration.

A safe prospective contract would use one exact serialized-byte budget and the existing source-line cursor: shrink only a source-page suffix, never silently drop individual calls from retained lines; error if one physical line and all its call metadata cannot fit. It would preserve full archive validation, bounded-memory overflow handling, stable hash-verified reads, relevant endpoint/path/range checks and legacy unflagged packets. Scoped unresolved-reference counts and explicit stored-evidence completeness must not imply semantic completeness. This design has not been evaluated by these runs, and the diagnosis provides no performance or quality claim for it.

Separately, task-independent evidence-reuse guidance could help avoid fetching declaration bodies again after equivalent source has already been read, while retaining useful relationship evidence and every semantic requirement. Batching callers addresses multiple incoming-impact questions, but cannot by itself replace requested source for declarations with no recorded callers. Neither direction justifies relaxing the current gate or changing these observations.

Tool-output bytes count receipts once; reported input is not the same measure and may include repeatedly supplied context and cached subsets. Final JSON bytes are likewise not total model output. Q1 has more tool-output bytes than C1 despite fewer reported tokens, illustrating why bytes alone cannot establish exact token causality. Two repetitions on this single, largely one-file operation do not establish general effectiveness or a counterfactual reduction in citation errors.

## Binding anchors

The raw answer/event hashes remain in the six unchanged review files named `javascript/semantic/javascript-express-download-transfer-{baseline,control,quotes}-{1,2}.json`. Their shared rubric and source-reviewed relationships were validated with these exact SHA256 anchors:

| Input | SHA256 |
| --- | --- |
| `javascript/SOURCE-REVIEW.md` | `addca2fd2c609caf8ca5a1ffd6fde2a721f09dd89d17c962cf06a2e0373b53a9` |
| `javascript/criteria.json` | `7a6cdcb63e238f860c53b4fd745291f9f1bb25b0162a712e0b8b4690150b9624` |
| `javascript/relationships.json` | `9fab97c0bdbd0dd10bcb152d78b27c81d2f4c58811bcd2fc31be7e4bce781e5e` |
| `recognize.py` | `1116e46f1fad5323de7d738c8c3498149ab3b99fae73e3705609c4690e7bca8f` |
| All three JavaScript graph archives | `e36126105e72f4a8399254b787bd80c329102e3d872120503721db8f9a943c0e` |

All observations, terminal artifacts, frozen inputs and prior reviews were read-only during this diagnosis. Only this supplemental document was created; no model was called and no raw trial artifacts were copied, rewritten or repaired by this task.
