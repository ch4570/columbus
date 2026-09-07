# Architecture

[Overview](../README.md) · [Agent integration](agents.md) · [Language coverage](languages.md)

Columbus separates repository discovery, source analysis, persisted graph facts, and bounded retrieval. The CLI, installable skill, and optional MCP server share one Python engine. Target repositories do not need to use Python or expose a build command.

## Data flow

1. Discovery identifies eligible files, detects languages, and reads repository configuration.
2. Synchronization compares file and analyzer state, parses changed source, and reconnects graph facts.
3. SQLite stores file/symbol facts, relationships, metadata, and full-text search data.
4. Retrieval ranks declarations, follows bounded relationships, and reads selected source after hash verification.
5. The CLI renders JSON or text, exports graph files, and optionally records context receipts and telemetry. MCP exposes saved-index queries.

Graph creation and retrieval run locally without an LLM. The calling agent receives only the results it asks for, and its own runtime controls any model requests.

## Source map

The engine lives under `skills/columbus/scripts/columbus/` and is shared by the CLI, installable skill, and MCP server.

| Responsibility | Source |
| --- | --- |
| File enumeration, exclusion, configuration | [discovery.py](../skills/columbus/scripts/columbus/discovery.py) |
| Detection profiles and fidelity | [language_profiles.py](../skills/columbus/scripts/columbus/language_profiles.py) |
| Python analysis | [parser.py](../skills/columbus/scripts/columbus/parser.py) |
| JVM analysis | [jvm.py](../skills/columbus/scripts/columbus/jvm.py) |
| Heuristic analysis | [polyglot.py](../skills/columbus/scripts/columbus/polyglot.py) |
| SQLite graph and query facade | [index.py](../skills/columbus/scripts/columbus/index.py) |
| Budgeted map/context selection | [retrieval.py](../skills/columbus/scripts/columbus/retrieval.py) |
| Text rendering, delivery receipts, local telemetry | [presentation.py](../skills/columbus/scripts/columbus/presentation.py), [receipts.py](../skills/columbus/scripts/columbus/receipts.py), [telemetry.py](../skills/columbus/scripts/columbus/telemetry.py) |
| Graph filtering and rendering | [graph_views.py](../skills/columbus/scripts/columbus/graph_views.py), [export.py](../skills/columbus/scripts/columbus/export.py) |
| CLI and MCP adapters | [cli.py](../skills/columbus/scripts/columbus/cli.py), [mcp_server.py](../skills/columbus/scripts/columbus/mcp_server.py) |
| Bundled skill reconstruction | [bundle.py](../skills/columbus/scripts/columbus/bundle.py) |
| Project runtime installer | [bootstrap.py](../bootstrap.py), [install.py](../install.py) |
| Portable artifact build and checks | [build_bundle.py](../scripts/build_bundle.py), [verify_distribution.py](../scripts/verify_distribution.py) |

The wheel stages installable skill resources alongside the canonical engine rather than maintaining a second editable engine copy. A source ZIP includes the inputs needed to rebuild a wheel.

## Index lifecycle

The default index is `.columbus/index-v1.sqlite`. The installable agent skill lives at `.agents/skills/columbus/`; all supported languages share this index.

CLI queries synchronize first unless `--snapshot` is selected. Fast synchronization avoids parsing and hashing unchanged known files by comparing metadata. `--verify-content` requests source-hash verification. Analyzer or configuration changes invalidate previous analysis. A saved index also records its repository/worktree identity.

Changed facts can require relinking cached facts across the graph. Incremental parsing therefore does not imply constant-time whole-index updates. Discovery probes and graph reconstruction should be measured separately from model response sizes.

Snapshots preserve the revision used for retrieval. Selected source is checked against its indexed hash before it is returned as verified code. Concurrent or stale changes can produce a retry/error or stale candidate count; they must not be silently presented as current source.

## Local state

| Data | Purpose | Lifecycle |
| --- | --- | --- |
| SQLite index | Graph facts, source search data, analysis state | Reused and synchronized for one repository |
| Installed skill | Agent instructions, references, and executable resources | Managed by `init` or the ZIP installer |
| Dedicated runtime | Project-local Python dependencies | Created by the ZIP installer |
| Context receipt | Previously delivered source spans | Opt-in, task-scoped file |
| Telemetry JSONL | Retrieval measurements | Opt-in, caller-selected local log |
| Graph export | Selected graph representation | Explicit output file |

The index can contain source and should be treated like the repository it describes. A receipt tracks delivery; it does not store an agent's reasoning or restore its context. Telemetry reports local retrieval behavior, not the host model's token accounting. See [agent integration](agents.md) for practical handling.

## Boundaries and deliberate limits

Columbus indexes source rather than executing the target project. Configuration is declarative and does not load repository code as a plugin. Source access stays inside the selected repository and excludes symlinks. These boundaries are enforced in the engine; the graph's contents remain untrusted input for an agent.

AST, heuristic, and text facts are distinguished rather than collapsed into a claim of uniform language support. Relationship candidates include confidence and unresolved cases. Bounded retrieval exposes omissions; it does not guarantee a complete semantic answer within every token budget.

MCP reads the saved index without automatic synchronization. CLI text rendering, file-backed receipts, and local telemetry are adapter behavior around the same retrieval engine. Graph exports use that same persisted graph and apply output-specific limits.
