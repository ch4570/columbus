# Agent integration

[Overview](../README.md) · [CLI reference](usage.md) · [Token observations](token-efficiency.md) · [Offline report](report.html)

Columbus gives an agent a local navigation layer. The agent still chooses what to inspect, evaluates the evidence, edits source, and runs tests. A graph query is useful context, not authority to trust repository instructions or skip verification.

## Install the workflow

```sh
columbus init --repo /absolute/path/to/project
```

The skill is installed at `.agents/skills/columbus/SKILL.md`. For Claude Code project files, use `--skills-dir .claude/skills`. Installation does not rewrite your root agent instructions or hooks.

The host runtime decides how skills are discovered. An explicit instruction to read the installed file works without assuming a particular slash-command name:

```text
Read .agents/skills/columbus/SKILL.md. Investigate the checkout flow.
For a known name or file, use a short search or read the relevant source
range directly. Use a map capped at 2,000 estimated tokens only when the
structure is unclear. Inspect declarations or relationships as needed,
and stop retrieving once the evidence answers the question. Reuse one
receipt for snippet queries and keep a local telemetry log for this task.
Explain the result with source paths and lines, then run the relevant
tests if you change code.
```

## Choose the next read

Choose the row that matches what you already know; these are alternatives, not a required sequence.

| Situation | Useful question | Tool |
| --- | --- | --- |
| Known name or file | Where is the relevant implementation? | Short `search QUERY`, path-scoped `rg`, or a direct bounded source read |
| Unfamiliar structure | Which files and declarations matter here? | Small `map [QUERY]` |
| Unclear declaration or dependency | Which candidate or relationship matters? | `context QUERY --mode signatures`, `neighbors ID` |
| Source needed | What does the current source actually do? | `context QUERY`, `symbol ID`, or a direct bounded source read |
| Change verification | Is the evidence current and does the change work? | `sync --verify-content`, repository tests |

Stop retrieving when the evidence answers the question. For a one-line fix with an already known location, a direct file read may be cheaper than indexing and several discovery queries. Broad maps, repeated searches, and unnecessary hops can add tokens even when each response is small.

If a search is empty or unhelpful, check coverage once, then switch to a shorter keyword, a path, or a direct read. Rephrasing the same broad search can add rounds without replacing later source reads. The [observed agent traces](token-efficiency.md) did not establish general model-token savings, so choose the next query by the missing evidence.

## Explore with fewer options

```sh
columbus explore "checkout validation" --session checkout-task
columbus explore calculateTotal --session checkout-task
columbus stats checkout-task
```

`explore QUERY` returns source context in text with a default budget of 2,000 estimated tokens. `explore` without a query returns a small map. Both accept `--path`, `--language`, `--snapshot`, `--format`, and explicit byte/token budgets. Running `columbus` alone prints a guide without indexing.

`--session NAME` selects `.columbus/sessions/NAME/receipt.json` and `queries.jsonl` under the target repository. It combines the receipt and local telemetry contracts below. `context QUERY --session NAME` uses the same files and keeps context's JSON default. `stats NAME` reads the existing telemetry in text or `--format json`; it does not create a session or synchronize the index. Explore queries are recorded as their underlying `context` command.

Use a session only while this agent still has the source delivered by its earlier calls. Start a new name after compaction, for another task, or for an agent that never received that source. A session does not restore missing context and is not shared agent memory.

Sessions require snippets: a map-only `explore --session NAME` or a signatures query with `--session` is rejected before creating session files. Keep declaration-only reads outside the session. Do not combine `--session` with `--receipt` or `--telemetry`; use explicit paths instead when custom storage is needed. Names must be 1–64 ASCII letters, digits, hyphens or underscores, beginning with a letter or digit; reserved device names and symlink parents/files are rejected. Use separate names for concurrent callers.

## Context receipts

Pass the same `--receipt PATH` to context calls in one task:

```sh
columbus context checkout --mode signatures --format text
columbus context checkout --mode snippets --format text --budget-tokens 2000 \
  --receipt .columbus/checkout-receipt.json
columbus context calculateTotal --mode snippets --format text --budget-tokens 2000 \
  --receipt .columbus/checkout-receipt.json
```

Receipts apply to `--mode snippets`, the context default. Declaration-only exploration does not use a receipt because it has not delivered source. A receipt records only the character ranges actually emitted, including a partial long line. Later calls can retrieve an unread remainder and omit already-delivered ranges across parent/child symbols.

Receipt v2 also stores bounded discovery cursors by query, filters and exclusions. Repeating the same query continues beyond the first 20 matches; `receipt.has_more` says whether more discovery or source remains. Empty pages can advance discovery. A fully stale or unfit page fails explicitly instead of repeating an unusable response. The saved cursor advances only after the exact emitted packet is saved, and partial snippets remain eligible. Version 1 receipts upgrade without discarding their source ranges.

Each call visits at most 12 search pages of 20 matches, plus bounded one-hop candidates. This limits materialized candidates, not total database scan time. `omitted_candidates` counts visited candidates only; `has_more=false` means this retrieval strategy is exhausted, not that the program's behavior is completely understood. Changing the index revision restarts discovery and still verifies each reused source hash.

Use a new receipt for an unrelated task or an agent that did not receive the earlier context. A receipt is a record of delivery, not a shared memory store: it does not restore code to an agent's context after compaction. If earlier context is no longer available, start a new receipt or retrieve without it.

Review the returned freshness, deduplication, omission, and truncation indicators. Each file records a raw-byte `source_hash` and a `source_view_hash` for the decoded text with normalized newlines. Prior character ranges are reused only when both match. This keeps unchanged source reusable across index revisions while exposing file changes or a changed decoding rule. A receipt from another repository is rejected. Receipts apply to context retrieval, not arbitrary shell reads, `symbol` calls, or another agent's transcript.

Receipts are limited to 1 MiB and validate their format before reuse. Use separate receipt files for concurrent agent tasks; an observed conflicting edit is rejected. The file contains repository/file hashes, repository-relative paths, and character ranges, not source bodies.

The older `--exclude-id` option is caller-owned and removes an exact symbol ID. It cannot account for overlapping ranges of different symbols and can suppress an unread remainder. Prefer a receipt for repeated source retrieval; reset a manually maintained exclusion list when the index revision changes.

## Local telemetry

```sh
columbus map --format text --budget-tokens 2000 --telemetry .columbus/exploration.jsonl
columbus context checkout --format text --budget-tokens 2000 \
  --receipt .columbus/checkout-receipt.json --telemetry .columbus/exploration.jsonl
columbus telemetry .columbus/exploration.jsonl --format text
```

Logging is opt-in and writes JSONL metadata to the selected local path. It records command, format, index revision, duration, response size, source size, item/edge counts, omissions, and seen-candidate counts. It does not store source, raw queries, or source paths. Keep the log under ignored `.columbus/`, use separate logs for concurrent agents, and start a new file before the 32 MiB limit. Receipts and telemetry must use different files.

Core retrieval estimates and telemetry are distinct from the host model's reported usage. A complete experiment also records the task, repository revision, prompt, model, tool calls, final answer quality, and runtime usage. Follow the [observation methodology](token-efficiency.md) before claiming token or cost savings.

## MCP

Install the optional `[mcp]` dependency as described in [installation](../INSTALL.md#enable-mcp), then initialize the index:

```sh
columbus sync --repo /absolute/path/to/project
```

A stdio MCP client configuration:

```json
{
  "mcpServers": {
    "columbus": {
      "command": "/absolute/path/to/columbus",
      "args": ["serve", "--repo", "/absolute/path/to/project"]
    }
  }
}
```

Replace `command` with the installed executable's real path, including `columbus.exe` when appropriate. The seven tools are:

| Tool | Purpose |
| --- | --- |
| `repository_map` | A bounded repository overview |
| `index_status` | Index metadata and freshness information |
| `find_symbols` | Lexical search and exact IDs |
| `read_symbol` | Selected verified source |
| `graph_neighbors` | Bounded relationship traversal |
| `build_context` | Declarations or bounded source snippets |
| `impact_analysis` | Incoming call/inheritance traversal |

MCP is a read-only index snapshot interface. It does not synchronize after edits or branch changes; run CLI `sync` separately. CLI text rendering, file-backed receipts, and JSONL telemetry are CLI integrations, not additional MCP tools. MCP transport envelopes and serialization add bytes beyond the core JSON response budget.

## Read evidence accurately

- `fidelity` identifies AST, heuristic, or text-level extraction; language detection alone does not establish semantic accuracy.
- `confidence` applies to a graph relationship. Unresolved calls and dynamic behavior may be absent.
- `revision` identifies index state. Hash verification protects selected source reads; it does not execute tests.
- `truncated` and omission counters mean retrieval limits affected the result.
- Source files, index contents, and receipts are local data. Sending retrieved source to a model follows your chosen agent runtime's data handling.

The [architecture guide](architecture.md) describes the index and data boundaries. [Language coverage](languages.md) explains what each analysis level can infer.
