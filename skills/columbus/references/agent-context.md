---
title: Budgeted agent context
source: ../scripts/columbus/retrieval.py
last_fetched: 2026-09-07
skills: [columbus]
---

# Budgeted retrieval

`map` ranks declarations by incoming non-containment dependencies; a query uses exact-name and FTS lexical ranking. It emits signatures/locations, no source bodies. The selection is bounded to 200 candidates (50 with a query); inspect `truncated`.

`context --mode signatures` combines lexical results and one-hop calls/inheritance/imports without source-body reads. `--mode snippets` verifies selected file hashes and returns at most 80 lines per candidate within the total budget. Whole-file matches can search beyond the first 12,000 characters and choose an excerpt around the query. Overlapping line ranges are emitted once.

`--exclude-id` removes already-seen candidate IDs. Exclusions are caller-owned, do not persist, and do not imply source verification. They filter exact symbol IDs, not every overlapping parent/child ID in the file. Excluding a truncated symbol also excludes its unread remainder. Reuse them only while `revision` is unchanged. Source read failures increment `stale_candidates`; no stale source is returned as verified.

`--budget-bytes` accepts 2048–64000. `--budget-tokens` accepts 700–21000 and tightens the byte cap to `min(budget_bytes, tokens * 3)`. The budget measures the complete selected format: compact JSON with no trailing newline, or text with its full header, accounting, policy line, and newline. Use `--format text` for agent reading; JSON remains the default. `estimated_tokens` is `ceil(UTF-8 bytes / 3)`, not an exact model tokenizer. MCP adds its envelope/serialization overhead.

`economy.indexed_source_bytes`, `response_bytes`, and `source_bytes_returned` enable reproducible payload comparisons. They do not establish real task-quality or model-cost savings. Use an equal-task model-usage experiment for those claims.

## Source receipts and observation

`neighbors`/`impact` and their MCP tools bound complete core JSON/text to 12,000 bytes by default, with the same 2048–64000 byte / 700–21000 estimated-token options. Navigation nodes omit full docstrings; signatures and edge evidence use at most 240 UTF-8 bytes. Inspect `omitted_text_bytes`, `omitted_nodes`, `omitted_edges`, `traversal_truncated` and `payload_truncated`. A retained edge always has both endpoint IDs. These public response budgets do not change the internal traversal used by focused exports or context candidate selection. MCP envelopes add transport bytes.

The CLI shortcut `explore [QUERY]` selects text output and a 2,000 estimated-token default; an explicit byte/token budget replaces that default. With no query it returns a map. `explore QUERY --session TASK_NAME` or `context QUERY --session TASK_NAME` selects `.columbus/sessions/TASK_NAME/receipt.json` and `queries.jsonl`. `stats TASK_NAME` reads the log without synchronizing or requiring an index. Names must be safe single path segments; session directories cannot traverse symlinks. A session cannot be combined with caller-specified receipt/telemetry paths or used for maps/signatures. Choose a fresh name after context loss or an agent change.

`context --receipt PATH` is a CLI snippets-only feature. It stores repository identity, revision, raw-file hash, normalized decoded-view hash, and half-open character ranges actually delivered. Reusing a receipt skips already delivered ranges across overlapping symbol IDs and continues unread parts of truncated symbols/lines. If bytes or decoding change, the affected spans are not reused. Legacy raw-only receipts safely re-emit source before upgrading.

Receipt v2 adds query/filter/exclusion-scoped discovery cursors. If the task still needs source, repeat while `receipt.has_more` is true; each call scans at most 12 pages of 20 lexical matches plus bounded nearby candidates. Stop earlier when the task contract is satisfied. Partial source keeps its page eligible. Empty pages can advance discovery; stale-only or unfit pages fail with an actionable error. Cursors are saved only with the exact delivered response. Revision changes restart discovery; old source hashes are still checked. Version 1 receipts upgrade while retaining their spans. Exhaustion is a retrieval state, not semantic completeness.

`search` and MCP `find_symbols` return `next_cursor`; pass it as `--cursor` or the tool's `cursor` argument with the same query and filters. A cursor from another revision, repository or scope is rejected. Page size may change. The cap limits returned candidates, not all database ranking work.

Receipts do not restore agent memory. Use a fresh file after a new task, agent handoff without the old source, or context loss. Use separate receipts for concurrent callers. Place files under `.columbus/` to keep them out of the source index. Existing invalid/unrelated files are preserved.

`--telemetry PATH` records only command, format, revision, timing, output/source byte counts, estimated tokens and result counters. It contains no query, file paths, or source text. `telemetry PATH --format text` summarizes the JSONL log. For actual model accounting, observe provider/runtime input, cached input subset, and output separately; never add cached input to total input again.

Prefer direct literal lookup for a known error/file; prefer graph navigation for structure and connected code. A forced graph step can cost more model interactions than a short `rg`. Do not repeat unsuccessful graph searches without checking coverage.

## 리뷰 훅

- Does the complete payload fit, including Unicode and metadata?
- Are source hashes, graph revision, omissions, and estimates distinguished?
- Have exclusions been cleared after a revision change?
