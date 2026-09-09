# Prospective compact-output evidence

These two versioned, read-only verifiers prepare a **new** comparison of compact archive outputs. They are not a cohort, launch authorization, model result, or replacement for a completed evaluation. No historical recognizer, runtime, input inventory, observation, review or gate is changed. Existing cohort adapters do not import these modules.

| Module/API | What a receipt proves | What it does not prove |
| --- | --- | --- |
| `call_table_evidence.evidence(events, *, binding, relationships)` | A successful explicit `archive-source --call-sites --call-table --format text` event delivered the exact expected source page and complete stored calls; a relationship receipt additionally matches an independently supplied reviewed relationship | Semantic understanding, runtime completeness, exact quotation from escaped text, answer quality or lower model cost |
| `search_batch_evidence.evidence(events, *, binding)` | A successful `archive-search QUERY QUERY …` event delivered every expected ordered discovery group in canonical JSON or text | Source delivery, a reviewed graph relationship, resolved ambiguity or task-relevant understanding |

`call-table-evidence-v1` emits source-call delivery receipts and, only for matched reviewed edges, relationship receipts. `call_table_used` means validated delivery, not that the final answer used it correctly. A valid empty-call page can have a delivery receipt without relationship utility.

`search-batch-evidence-v1` emits only `search_batch_receipts`. Its `useful_discovery` field means that at least one candidate was returned, not that the candidate is useful for the task. Valid zero-match groups remain in their complete response; an entirely empty batch can have a receipt with `useful_discovery=false`. Candidate occurrences across overlapping groups remain distinct from unique IDs. Discovery receipts must never populate source-delivery or relationship-utility fields.

## Independent binding and comparison

Both APIs require the exact seven-key binding used by the unchanged `source_call_evidence.py`:

- Absolute `repository` and `archive` paths, with repository, archive and runtime separated.
- Exact `invocation_prefix`: absolute Python executable, `-B`, absolute runtime wrapper.
- Independently frozen `archive_sha256`, `revision`, complete `source_manifest`, and complete `runtime_inventory` relative to the wrapper directory.

The binding must come from independently frozen inputs, **not from the files being assessed**. The caller remains responsible for freezing the verifier and its unchanged helper, the interpreter/CLI environment, runtime, sources and archive. A command string or a runtime inventory alone does not attest that an executable actually ran; the collector must retain and validate actual terminal event streams and the whole-command review.

Each verifier checks complete frozen inventories and archive bytes before recognition, including for empty or failed event streams. It revalidates the captured source/runtime inventories and archive bytes after recognition; timestamp-only equality is insufficient for this final check. Invalid frozen inputs fail with `ValueError`. Unsupported, failed, incomplete or byte-inconsistent events receive no receipt. A final binding failure is not converted into a successful empty result.

The command parser permits the exact Python prefix directly or one explicit `-c`/`-lc` wrapper at `/bin/sh`, `/bin/bash`, `/bin/zsh`, `/usr/bin/sh`, `/usr/bin/bash` or `/usr/bin/zsh`. Bare names and arbitrary paths sharing those basenames are rejected. This is a supported-syntax boundary, not binary provenance. Expansion, chaining, redirection, duplicate/unsupported options and ambiguous abbreviated flags are not interpreted or executed.

Expected results are reconstructed from immutable graph/source records using independent code, not the production selector or renderer. The unchanged legacy verifier supplies frozen-input, source-decoding, selection, endpoint projection, source-packet construction and safe-parsing primitives. The new modules neither import/execute offered runtime or repository code nor launch a subprocess/model or write files. Tests may execute an isolated copied runtime on tiny fixtures to obtain actual control outputs; this is separate from verifier execution.

## Complete output contracts

Call-table verification binds the ordered query list, overload selection, source offset/limit, format and shared byte budget. It independently checks the source union, actual nested owners, all ordered duplicate edges, full endpoint identities/ranges/hashes, reference counts, unknown `partial`, archive-only status and cursor. Source-file and call-file index namespaces are separate and local to a page. Terminal-safe source text is reconstructed from frozen source, never reverse-unescaped for quotation.

Per-line zero-index edge rows, unique endpoint rows and shared file rows establish the table-mode flood bound. Legacy full-ID edge costs and the raw hydrated-node 64-KiB cap are not valid bounds for this format. The independent fitter checks decreasing complete source-page prefixes using final escaped UTF-8 bytes and the final newline, without assuming monotone serialized sizes. It does not drop individual calls or skip an unreturnable next line. The independent query-candidate capacity remains in force.

Batch discovery binds 2–16 distinct ordered queries, common path/language filters, per-query limit, format and one shared budget. It reproduces exact/qualified/substring ranking, full declaration projection including signatures and hashes, diagnostics, match counts, truncation and every ordered group. Function/module ties remain candidates rather than resolved declarations. No group or candidate is removed merely to fit the batch budget. A complete response that exceeds the budget has no receipt.

These offline verifiers intentionally load a complete frozen snapshot and rehash inputs. They do not implement the production query's streaming-memory limit, and their CPU, I/O or storage is not candidate model-token cost.

## Before any new model comparison

Create a separate cohort adapter and freeze its full dependency closure, runtime commits/delta, cases, source/archive inventories, exact CLI/environment, schedules and capability controls. Bind both new verifiers and the unchanged helpers they import. Capture fresh controls from the selected runtime capabilities; do not assume that a newer control lacks call-sites merely because an older control did.

Call-table controls must cover index/path/hash/owner/cursor/reference corruption, omitted/duplicated calls, page-local index reuse, legacy parity, real floods and long shared IDs that fit only the table bound. Batch controls must cover reordered/omitted groups, wrong filters/ranking/counts/truncation, zero matches, overlaps, ambiguity and whole-batch overflow. Both need actual successful invocation controls, failed/offered/empty event negatives and frozen-input mutation checks.

Preserve the strict acceptance obligations: **all six primary pairs must strictly reduce both actual total input and actual total output; all 18 runs must pass full semantic, citation, execution and terminal review; all 12 graph-arm runs must contain a reviewed useful relationship**. Secondary comparisons, table adoption, discovery receipts, bytes, cache counts, averages and command counts cannot compensate for a failed obligation. No reruns, replacement observations, omitted failures or retrospective regrading.

The completed study remains unchanged at 0/6 primary and 0/6 secondary accepted pairs; candidate aggregate input was +39.02% and output +24.77%. Fixed-packet byte reductions are motivation, not proof that these costs improved. A combined-feature study cannot isolate the effect of one feature. New preparation/launch must also satisfy the existing 384-MiB preparation and 256-MiB remaining-reserve guards; this verifier work does not waive them.
