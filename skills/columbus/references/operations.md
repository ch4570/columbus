# Installation, visualization and MCP

Read this reference only for these operations. The installed skill bundle and repository index are separate: updating one does not synchronize the other.

## Install or update

Use `columbus init --repo REPO`; `--plan` is read-only. Preserve managed-file conflicts. A downloaded ZIP's `install.py --repo REPO` also creates a dedicated runtime. See [bundle synchronization](bundle-sync.md) for ownership and recovery details. Use the actual installed entrypoint/interpreter rather than inventing a path.

## Bounded visual export

`graph --repo REPO --format mermaid --level file --kinds calls imports --output NEW_PATH` creates a bounded graph view. JSON, Mermaid, GraphML and offline HTML are supported. Select scope with `--focus ID`, `--hops`, `--path` or `--language`. Existing files are not overwritten. For every indexed node/edge rather than a bounded view, use the [complete archive](archive.md).

## Saved-snapshot MCP

Install the optional `mcp` extra, run `sync --summary`, then `serve --repo REPO`. Seven tools read a saved snapshot; they do not auto-sync or execute repository code. Use `find_symbols` for known names or `repository_map` for orientation, then `build_context` as needed. Synchronize through the authorized CLI after changes. MCP transport adds overhead beyond CLI byte budgets.

Report IDs/locations, relationship evidence, revision and remaining uncertainty without dumping the full graph. Python/Java/Kotlin AST extraction is not compiler or runtime equivalence; other language fidelities vary. See [language fidelity](polyglot.md) and [JVM analysis](jvm-analysis.md).
