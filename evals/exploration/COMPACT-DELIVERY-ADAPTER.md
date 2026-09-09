# Prospective compact-delivery adapter

`compact_delivery_adapter.evidence(events, *, binding, relationships)` combines four existing read-only verifiers for a **future** comparison. It does not change a historical cohort adapter, launch a study, grade an answer or establish savings. The adapter version is `compact-delivery-adapter-v1`; nested receipts keep their original verifier versions, fields and hashes.

| Delivery lane | Unchanged verifier | Separate adoption flag |
| --- | --- | --- |
| Full-ID source/calls, JSON or text | `source_call_evidence.py` | `full_id_source_calls_used` |
| Explicit text call table | `call_table_evidence.py` | `call_table_used` |
| Default or explicit JSON call table | `json_call_table_evidence.py` | `json_call_table_used` |
| Batch search, JSON or text | `search_batch_evidence.py` | `search_batch_used` |

`source_calls_used` is aggregate adoption across the first three lanes. `source_call_receipts` contains their complete source/call deliveries. `relationship_receipts` and `relationship_used` require an independently supplied reviewed relationship present in those delivered calls. `search_batch_receipts` remains discovery only and never populates either source or relationship receipts. An accepted all-zero batch sets `search_batch_used=true` while its existing `useful_discovery=false`; even nonempty discovery does not prove task relevance.

Each receipt list follows the original terminal-event order, not format-group order. A source delivery and its backed relationship receipt describe one command, not two executions. Ordered duplicate edges inside a packet remain part of its complete output and stored-edge count; the adapter never deduplicates them. It does not sum receipt lists into an execution count, quality score or utility score.

## One stream, one command-ID namespace

Pass one trial's complete decoded event stream, not concatenated trials whose IDs may restart. Every top-level `item.completed` record with a `command_execution` item and nonempty string ID reserves that ID **before** command parsing, success checks or lane selection. A second such terminal record with the same ID raises `ValueError`, including identical duplicates, failed-to-successful rewrites, malformed exit codes and unsupported commands. No observation is silently discarded to resolve the conflict. Keep the original raw capture for investigation; rejection is not permission to repair, omit or rerun a trial.

An `item.started` or `item.updated` record followed by one terminal record is normal. Unsupported or byte-inconsistent commands receive no receipt, but they are not erased from the captured stream and remain subject to duplicate-ID checks and the caller's whole-log execution review.

The adapter consumes one-shot iterables once and independently captures each yielded event before requesting the next. Each event must be a plain JSON object whose nested values are valid JSON transport values, with string object keys, finite numbers and no cycles or unsupported Python objects. Invalid transport fails the adapter rather than being normalized into a different event or silently skipped. Reusing and mutating the same dictionary between yields cannot rewrite an earlier captured event.

## Strict binding and dispatch

Use the exact seven-key independently frozen binding described in [the compact-output evidence contract](COMPACT-EVIDENCE.md#independent-binding-and-comparison). Capture binding and reviewed relationships before consuming events. The adapter validates complete source/runtime inventories and archive bytes before event iteration and again in a whole-pipeline `finally`, including empty streams, duplicate-ID rejection and iterator/verifier exceptions. Closing input-equality checks follow the last filesystem I/O. A final integrity failure raises; it cannot become a successful empty result.

All four unchanged standalone verifiers examine the captured stream using their quote-aware complete-command parsers and independent canonical-output reconstruction. There is no substring/header dispatch and no snapshot-skipping fast path. The adapter additionally rejects overlapping delivery ownership or a relationship receipt without its same-command, same-binding source receipt. Existing lane-specific syntax stays unchanged: new table/batch lanes retain their exact absolute-shell allowlists, while the historical full-ID lane retains its historical parser. Supported shell syntax and command hashes are not executable provenance.

The adapter imports local verifier dependencies through path-isolated names; it never executes the offered runtime or repository, launches a subprocess/model or writes files. It retains the full captured stream and invokes four strict offline verifiers in addition to its outer integrity checks. This adds offline memory and I/O; it is not a production streaming-memory guarantee or a model-token optimization.

## Integration remains a separate step

Existing cohort adapters, dependency manifests, controls, observations and reviews are unchanged. Before a new actual comparison, create a separate cohort copy and explicitly freeze this adapter, all four verifiers, their transitive helpers, fixture/control dependencies, runtime/interpreter/environment, cases, schedules and source/archive inventories. Preserve existing neighbor/caller/quotation recognition when integrating; this adapter does not replace those lanes. Capture fresh runtime-capability and corruption controls, including mixed streams, duplicate IDs, failed calls and input mutations.

Review new runtime pins/deltas and graph provenance separately. The historical graph-reuse proof requires byte-identical analyzer modules; a changed analyzer cannot inherit that proof merely by updating a commit. The 384-MiB preparation and 256-MiB remaining-disk reserves still apply. Adapter tests do not waive either boundary.

Acceptance remains **all six primary pairs strictly lower on both actual total input and output, all 18 full semantic/citation/execution/terminal reviews, and all 12 graph-arm runs containing a reviewed useful relationship**, with complete schedules and inventories. Secondary pairs, adoption, discovery, bytes, averages or cached tokens cannot compensate. No replacement runs, omitted failures or retrospective regrading.

The completed study remains 0/6 primary and 0/6 secondary accepted pairs, with candidate aggregate input +39.02% and output +24.77%. This future-only adapter changes none of those observations or conclusions.
