# Named snippet session budgets

Opt in **on a new session's first query**. Each limit is optional and is an integer from 1 through 2^63−1:

```sh
columbus explore checkout --session checkout-task --max-queries 8 --max-session-bytes 24000 --max-no-progress 2
columbus explore validation --session checkout-task
columbus stats checkout-task --format json
```

The second command inherits the saved limits even though it omits the flags. The policy is immutable: repeating the same values is allowed; changing or adding a limit to that policy is rejected. A previously used unbudgeted session cannot acquire a budget retrospectively. Queries without a policy keep their existing behavior.

## What is counted

- `max_queries`: admitted queries, including attempts that fail during sync/retrieval or delivery. Rejected admission does not consume another query.
- `max_session_bytes`: cumulative complete UTF-8 **stdout query payloads**. Each response is capped at the smaller of the ordinary per-response budget and the remaining allowance. A remainder below the engine's 2,048-byte minimum rejects admission before sync/source reads.
- `max_no_progress`: consecutive admitted queries without new source or an advancing continuation cursor. Failed pre-output attempts and repeated exhausted/seen-only results increment it; new source or advancing empty discovery pages reset it. Revision changes do not reset cumulative usage. A changed revision with no evidence is not progress by itself.

Admission exhaustion returns exit **3**, empty stdout, and a bounded stderr diagnostic with reason, usage, policy, remaining bytes and next-step guidance. Other invalid/uncertain states return exit **2**. Budget exhaustion is not source exhaustion, and neither proves task completion. `receipt.has_more` describes remaining retrieval candidates, not whether the task has enough evidence. Review retained evidence and the task contract before changing the entry point; do not loop around the limit automatically.

Only `context QUERY --session NAME` and `explore QUERY --session NAME` snippets are governed. stderr diagnostics, `stats`, map/search, direct `--receipt`, shell reads, MCP envelopes/calls, other agents, model input/cache/reasoning and provider charges are **outside this cap**. A new name starts an independent ledger, not a task-wide billing reset. After compaction or an agent change, use a fresh receipt to avoid omitting evidence the agent no longer has, but carry the earlier cost forward in host-side task accounting. Do not manufacture new names to evade a task's intended allowance.

## Delivery, failure and ownership

The session directory contains `budget-policy.json` (ownership/policy marker), `budget.json` (authoritative usage) and, while a caller is active, `.budget.lock`. No query text, source text or source path is added to these budget files. A repository identity hash, last successful revision and receipt digest bind accounting to the same session.

All named callers take an exclusive lease, including callers without budget flags. Concurrent callers are explicitly rejected. The lease spans admission, sync, retrieval, stdout flush, receipt save and usage finalization. A process never steals another caller's lock.

Admission durably reserves the response allowance before sync. A pre-output failure consumes a query and one no-progress step but releases the byte reservation. Immediately before stdout, the reservation is narrowed to the exact rendered payload. After stdout flush and receipt save, that payload is charged and the reservation released **before** optional telemetry append. A telemetry failure can therefore return exit 2 after successful, already-accounted delivery; inspect stats/retained stdout before retrying.

A crash/write/flush/receipt-save failure during delivery leaves `phase=pending`: the reserved bytes may have been delivered, so they are not silently counted as zero or retried. `stats` exposes completed usage separately from held bytes and the observational query log. If the process died, its lock may remain; after independently confirming there is no active caller, archive the entire affected session for inspection. There is no automatic unlock, reset, budget increase or pending-delivery recovery command. Starting an explicitly separate task/session does not erase the old held usage from task-level accounting.

Missing/corrupt/inconsistent policy or usage files, changed receipt hashes and wrong repository ownership fail closed. Keep the entire session directory together; don't edit/delete individual state files. These are local cooperative controls, not tamper-proof enforcement against a filesystem owner who deletes all evidence. `stats` is read-only and works without an index or successful telemetry rows, but reports invalid state rather than fabricating zero usage.

If optional telemetry is empty, partially written, corrupt or unreadable while the budget is valid, `stats` still returns `session_budget`. It marks `telemetry_status=unavailable`, reports the error, and leaves observational totals as `null`, not zero or partial totals. The log and session state are preserved. Invalid budget state remains an error; this fallback does not repair logs or relax query admission.
