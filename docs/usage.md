# CLI usage

[Overview](../README.md) · [한국어](usage.ko.md) · [Installation](../INSTALL.md) · [Agent workflow](agents.md)

Run commands inside the target repository or pass `--repo /absolute/path/to/project`. Running `columbus` without arguments prints a short guide and does not create an index. `explore` defaults to compact text; existing query commands keep their JSON default.

## Start with one command

```sh
columbus explore
columbus explore "checkout validation"
columbus explore checkout --session checkout-task
columbus stats checkout-task
```

`explore` returns a repository map when no query is supplied. With a query, it returns snippet context. Both default to 2,000 estimated tokens, including metadata. Add `--format json` for structured output. The index synchronizes automatically; `--snapshot` reads an existing snapshot.

A named session automatically uses `.columbus/sessions/checkout-task/receipt.json` and `queries.jsonl` under the selected repository. Later source queries with the same session omit already-delivered ranges and record local response measurements. Sessions are optional: use a new name for a new task, after context compaction, or when another agent has not received the earlier source.

`stats NAME` reads that session's measurements in text, or JSON with `--format json`. It never creates records or synchronizes the index, and works even if the index was removed. A missing session returns an error without creating files.

## Find an entry point

```sh
columbus map --format text --budget-tokens 2000
columbus search checkout --format text --limit 5
columbus context checkout --mode signatures --format text --budget-tokens 1500
```

An unfiltered map ranks declarations using incoming non-containment relationships. A query uses exact-name and lexical search. These are retrieval signals, not a semantic proof of relevance. Inspect the returned paths and signatures before choosing a symbol.

Search returns `next_cursor` when another page exists. Pass that value with `search QUERY --cursor CURSOR` and the same filters; changing the index revision requires restarting. Page size can change. Context receipts manage their own continuation: repeat the same snippet query while `receipt.has_more` is true. Partial source is retained, and exhausted retrieval does not imply complete semantic coverage.

| Query | Returns | Source-body reads after synchronization |
| --- | --- | --- |
| `explore` | Small repository map in text | None |
| `explore QUERY` | Budgeted snippet context in text | Selected files |
| `map [QUERY]` | Ranked declarations, locations, coverage | None |
| `search QUERY` | Matches and exact symbol IDs | None |
| `context QUERY --mode signatures` | Declarations and nearby graph candidates | None |
| `context QUERY --mode snippets` | Selected, hash-verified source spans | Selected files |
| `symbol EXACT_SYMBOL_ID` | The selected declaration's current code | Its file |

The first index reads source, and a later synchronization may read changed files. “None” in the table describes the retrieval step after synchronization.

## Read source and relationships

Use the exact `id` returned by a query:

```sh
columbus symbol 'EXACT_SYMBOL_ID' --max-lines 80 --format text
columbus neighbors 'EXACT_SYMBOL_ID' --hops 1 --kinds calls imports --format text
columbus impact 'EXACT_SYMBOL_ID' --hops 2 --format text
columbus context checkout --mode snippets --format text --budget-tokens 2000
```

`neighbors` accepts `--direction in|out|both`; the default is `both`. Relationship kinds are `contains`, `calls`, `imports`, and `inherits`. `impact` follows incoming `calls` and `inherits` relationships. Both are bounded graph views and may omit unresolved or dynamic behavior.

Source snippets are verified against indexed content hashes. A failed source check is not returned as verified code. Inspect stale and truncation indicators; narrow the query or synchronize again when necessary.

## Scope a query

`explore`, `search`, `map`, `context`, `graph`, and the legacy `export` alias accept path and language filters:

```sh
columbus search checkout --language typescript --path 'web/*' --format text
columbus explore checkout --language typescript --path 'web/*'
columbus context checkout --path 'web/*' --mode signatures --format text
```

Quote glob patterns so your shell does not expand them. Language values use detected lowercase names, such as `typescript`, `cpp`, and `csharp`. Configuration and unknown-language behavior are covered in [language coverage](languages.md).

## Bound the response

| Option | Allowed values | Meaning |
| --- | --- | --- |
| `--budget-bytes` | 2,048–64,000 | UTF-8 response budget for explore/map/context/neighbors/impact |
| `--budget-tokens` | 700–21,000 | A byte budget derived from `tokens × 3` |
| `--limit` on search | Query result limit | Limits candidate output |
| `--max-lines` on symbol | Source excerpt limit | Limits the selected source read |

Explore defaults to 2,000 estimated tokens, equivalent to 6,000 bytes. An explicit `--budget-tokens` or `--budget-bytes` replaces that default. If both are supplied, the smaller byte limit applies.

```sh
columbus explore checkout --budget-tokens 3000
columbus explore checkout --budget-bytes 2048
```

The existing `map` and `context` defaults remain 6,000 and 12,000 bytes. For these commands, increasing `--budget-tokens` alone does not raise the default byte limit; set both when a larger response is intended.

`neighbors` and `impact` also default to 12,000 bytes. Their nodes are navigation summaries without full docstrings; signatures and edge evidence are capped at 240 UTF-8 bytes. `omitted_text_bytes` records text removed from the count-selected graph before fitting; `omitted_nodes` and `omitted_edges` count payload removals. `traversal_truncated` preserves the original node/edge count-cap signal; `hops` separately selects traversal depth. `payload_truncated` identifies projection or byte-budget omissions, and `truncated` combines both signals. Retained edges always include both endpoint IDs. Byte-budgeted JSON stays compact even with `--pretty`.

```sh
columbus context checkout --budget-bytes 18000 --budget-tokens 6000 --format text
```

The budget includes accounting fields and other metadata in the selected JSON or text output. `estimated_tokens` uses `ceil(UTF-8 output bytes / 3)`, not a model tokenizer. Use the format-specific output accounting and telemetry for comparisons. MCP adds transport and serialization overhead outside the core response budget.

Inspect `truncated`, `omitted_candidates`, `stale_candidates`, and per-item excerpt limits. A small budget can omit useful candidates. Avoid treating a truncated packet as a complete repository description.

## Avoid repeating source

Use one session per task when the same agent needs more source:

```sh
columbus explore checkout --session checkout-task
columbus explore calculateTotal --session checkout-task
columbus stats checkout-task --format json
```

`context QUERY --session NAME` uses the same files and retains context's JSON default. Session names are 1–64 ASCII letters, digits, hyphens or underscores, starting with a letter or digit; reserved device names such as `CON` are rejected. Session directories and files cannot be symlinks. Do not combine `--session` with manual `--receipt` or `--telemetry` paths.

Sessions require source snippets. `explore` without a query and `--mode signatures` reject `--session` and create no receipt. Run declaration-only queries without a session.

For a new session, optionally persist cumulative limits with `--max-queries 8 --max-session-bytes 24000 --max-no-progress 2`. Omitted flags on later queries still use that immutable policy. Exhaustion returns exit 3 before sync/source reads, with no stdout payload; stderr explains the reason. These limits cover named CLI snippets only, not model billing or other tools. See [session budgets](../skills/columbus/references/session-budgets.md) for exact counting, failure/pending delivery, concurrency and recovery semantics.

For explicit file locations, use one receipt per task instead. `--mode signatures` does not accept receipts:

```sh
columbus context checkout --receipt .columbus/checkout-receipt.json --format text
columbus context calculateTotal --receipt .columbus/checkout-receipt.json --format text
```

Receipts track source character ranges delivered in earlier calls. They address overlapping parent/child symbols, repeated queries, and partial long lines, while a plain exclusion only removes an exact symbol ID. The [receipt contract](agents.md#context-receipts) explains freshness, partial output, and when to start a new receipt.

For callers that already track exact IDs, `--exclude-id` is repeatable:

```sh
columbus context checkout --exclude-id 'EXACT_SYMBOL_ID' --format text
```

An exact-ID exclusion also excludes an unread remainder of a truncated symbol. It does not exclude another ID with overlapping source. Clear caller-owned exclusion lists after an index revision change.

## Export a graph

```sh
columbus graph --format html --output graph.html
columbus graph --format mermaid --level file --kinds imports calls --output dependencies.mmd
columbus graph --format graphml --language typescript --path 'src/*' --output frontend.graphml
columbus graph --format json --focus 'EXACT_SYMBOL_ID' --hops 2 --kinds calls --output flow.json
```

| Option | Behavior |
| --- | --- |
| `--format json\|mermaid\|graphml\|html` | Structured data, document diagram, external-tool import, or offline view |
| `--level symbol\|file` | Declaration graph, or relationships grouped between files |
| `--focus ID` | Center on an exact symbol ID; an unambiguous name is also accepted |
| `--direction in\|out\|both` | Restrict relationship direction around a focus |
| `--kinds KIND ...` | Select relationship kinds |
| `--path GLOB`, `--language NAME` | Restrict graph scope |
| `--limit N` | Bound the exported nodes |

Full graph exports default to 1,000 nodes and allow up to 5,000. Focused views allow up to 200 nodes and 3 hops; edges are bounded as well. The response exposes truncation. Break large exports into scopes to retain relevant relationships.

The output file is created exclusively, so an existing file is not overwritten. Use a new path or explicitly remove your prior export. HTML is self-contained; it does not require a running Columbus server. `export` remains a compatibility alias for `graph`.

## Keep the index current

```sh
columbus sync
columbus status --verify-content
columbus sync --verify-content
```

Code queries automatically synchronize unless `--snapshot` is set. The startup guide, `stats`, and `telemetry` do not synchronize. Fast synchronization uses file metadata to avoid rehashing unchanged known files. `--verify-content` checks source hashes; use it when timestamps are not trustworthy or stronger freshness evidence is needed. Unknown extensions may still require a text-discovery probe, reported as `inventory.probe_files` and `inventory.probe_bytes`.

The index accounts for source, configuration, analyzer identity, and repository/worktree state. `--db PATH` selects another index file. A snapshot is tied to its recorded repository; it cannot silently stand in for a different root. MCP uses the saved snapshot and requires separate CLI synchronization after edits or branch changes.

## Observe a session

```sh
columbus explore checkout --session checkout-task
columbus stats checkout-task
```

Explore records its underlying `context` command in the session log. The summary reports output bytes, estimated tokens, source bytes, latency and counts. For custom log paths or map-only measurements, use the explicit telemetry option:

```sh
columbus map --format text --telemetry .columbus/exploration.jsonl
columbus context checkout --format text --receipt .columbus/checkout-receipt.json \
  --telemetry .columbus/exploration.jsonl
columbus telemetry .columbus/exploration.jsonl --format text
```

Telemetry is opt-in local metadata. It makes response volume and retrieval behavior inspectable; it does not read model billing. See the [observation guide](token-efficiency.md) for measurement definitions, paired exploration, and evidence.
