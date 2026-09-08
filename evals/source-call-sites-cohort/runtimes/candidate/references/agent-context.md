---
title: Budgeted agent context
source: ../scripts/columbus/retrieval.py
last_fetched: 2026-09-09
skills: [columbus]
---

# Budgeted retrieval

## Local navigation

- Direct callers: `callers IDENTIFIER --format text --context-lines 20 --budget-bytes 12000`; add the task's `--path` scope. Unique names or exact Python `module.qualname` work; search for an exact ID if ambiguous. Nested functions are separate callers.
- Other navigation: `search IDENTIFIER --format text --limit 5`, then `explore ID` for verified source. Follow `next_cursor` with `--cursor` and unchanged query/filters if more matches are needed; restart after a revision change. `map --format text --budget-tokens 2000` gives orientation. Check coverage once if empty, then use source search.
- All stored call sites: `neighbors ID --direction in --hops 1 --kinds calls --format text`. Incoming dependency paths: `impact ID --hops 3 --format text`.
- Repeated source: `explore QUERY --session TASK` skips delivered ranges and continues later matches. Repeat unchanged options while more evidence is needed and `receipt_continuation=more` (JSON `receipt.has_more=true`), even after an empty page. Sync if source is stale. Start a new session after context loss or handoff.

Add `--repo REPO` to local queries. They auto-sync unless `--snapshot` is requested; sync failure stops the query. After edits/tests use `sync --summary`, or `sync --summary --verify-content` for full hashing. Each worktree needs its own index.

## Bounded context

`map` ranks declarations by incoming non-containment dependencies; a query uses exact-name and FTS lexical ranking. It emits signatures/locations, no source bodies. The selection is bounded to 200 candidates (50 with a query); inspect `truncated`.

`context --mode signatures` combines lexical results and one-hop calls/inheritance/imports without source-body reads. `--mode snippets` verifies selected file hashes and returns at most 80 lines per candidate within the total budget. Whole-file matches can search beyond the first 12,000 characters and choose an excerpt around the query. Overlapping line ranges are emitted once.

`search --limit 1..50` returns `next_cursor`; pass it with `--cursor` and the same query, path/language filters and index revision. The limit may change between pages. Cursors are opaque, repository/snapshot-bound and not source verification. A changed revision requires a fresh search. Results are no longer capped at the first 150 lexical candidates.

`--exclude-id` removes already-seen candidate IDs. Exclusions are caller-owned, do not persist, and do not imply source verification. They filter exact symbol IDs, not every overlapping parent/child ID in the file. Excluding a truncated symbol also excludes its unread remainder. Reuse them only while `revision` is unchanged. Source read failures increment `stale_candidates`; no stale source is returned as verified.

`--budget-bytes` accepts 2048–64000. `--budget-tokens` accepts 700–21000 and tightens the byte cap to `min(budget_bytes, tokens * 3)`. The budget measures the complete selected format: compact JSON with no trailing newline, or text with its full header, accounting, policy line, and newline. Use `--format text` for agent reading; JSON remains the default. `estimated_tokens` is `ceil(UTF-8 bytes / 3)`, not an exact model tokenizer. MCP adds its envelope/serialization overhead.

`economy.indexed_source_bytes`, `response_bytes`, and `source_bytes_returned` enable reproducible payload comparisons. They do not establish real task-quality or model-cost savings. Use an equal-task model-usage experiment for those claims.

## Source receipts and observation

The CLI shortcut `explore [QUERY]` selects text output and a 2,000 estimated-token default; an explicit byte/token budget replaces that default. With no query it returns a map. `explore QUERY --session TASK_NAME` or `context QUERY --session TASK_NAME` selects `.columbus/sessions/TASK_NAME/receipt.json` and `queries.jsonl`. `stats TASK_NAME` reads the log without synchronizing or requiring an index. Names must be safe single path segments; session directories cannot traverse symlinks. A session cannot be combined with caller-specified receipt/telemetry paths or used for maps/signatures. Choose a fresh name after context loss or an agent change.

`context --receipt PATH` is a CLI snippets-only feature. It stores repository identity, revision, raw-file hash, normalized decoded-view hash, half-open character ranges actually delivered, and bounded discovery cursors. Reusing a receipt skips already delivered ranges across overlapping symbol IDs, continues unread parts of truncated symbols/lines, and advances beyond the first 20 lexical matches. If bytes or decoding change, the affected spans are not reused. Legacy v1 receipts upgrade on successful save; raw-only spans safely re-emit source before upgrading. Older engines reject v2 receipts; use a separate file when switching back.

Repeat the same query, mode, path/language and exclusions while more evidence is needed and `receipt.has_more` is true (text: `receipt_continuation=more`). An empty page can still have more results: one invocation examines at most 12 pages of 20 lexical candidates, plus bounded one-hop dependencies. `has_more=false` exhausts this retrieval strategy, not every semantic dependency. Omission counts describe visited candidates, not a repository-wide total. Stale source pins discovery for a retry after `sync`; if nothing can be delivered, retrieval fails explicitly instead of repeating empty success. Increase the budget or narrow the query if one source item cannot fit.

Discovery is scoped by a hash of query/mode/filters/exclusions; changing them starts independent discovery while preserving source deduplication. Budget and format may change. A revision change restarts discovery and still hash-checks returned source. At most 128 scopes are retained; eviction restarts discovery only. Opaque cursors remain in the receipt file, outside the model response budget; they may contain ranked symbol IDs but no raw query. Earlier pages are not revalidated on every continuation. Source files outside the visited candidates are not verified.

Python callers open a fresh `ReceiptFile` per query, pass its `.data` to retrieval, and save the unchanged result with that same instance before another query. An identical copied/JSON-roundtripped response is accepted; altered or unassociated responses are rejected. Plain dictionary receipts expose `continuation_scope`/`next_cursor` in the response, within its byte budget, for explicit state transfer.

Receipts do not restore agent memory. Use a fresh file after a new task, agent handoff without the old source, or context loss. Use separate receipts for concurrent callers. Place files under `.columbus/` to keep them out of the source index. Existing invalid/unrelated files are preserved.

`--telemetry PATH` records only command, format, revision, timing, output/source byte counts, estimated tokens and result counters. It contains no query, file paths, or source text. `telemetry PATH --format text` summarizes the JSONL log. For actual model accounting, observe provider/runtime input, cached input subset, and output separately; never add cached input to total input again.

Prefer direct literal lookup for a known error/file; prefer graph navigation for structure and connected code. A forced graph step can cost more model interactions than a short `rg`. Do not repeat unsuccessful graph searches without checking coverage.

## 리뷰 훅

- Does the complete payload fit, including Unicode and metadata?
- Are source hashes, graph revision, omissions, and estimates distinguished?
- Have exclusions been cleared after a revision change?

## Caller explanations

Use `callers TARGET --path 'src/*' --context-lines 20 --format text --budget-bytes 16000` when the task asks why callers invoke a target. The path glob filters caller identities before counting and applying the limit; it does not filter target lookup. Context lines (0–40) expand around the first call and stay inside its lexical caller. The default remains the compact call-site excerpt. Wider context can omit later calls or comments outside the caller; `call_sites` counts all stored calls in that caller, not only those shown. Check the numbered range, caller count and truncation before deciding whether another source range is necessary. A larger window can reduce the number of callers fitting the byte budget; no token saving is guaranteed.
