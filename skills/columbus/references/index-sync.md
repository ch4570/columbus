# Code index synchronization

## Command behavior

`columbus` is the portable entrypoint; `scripts/columbus.py` delegates to the same CLI. Its default DB is `REPO/.columbus/index-v1.sqlite`; use a separate directory per worktree. A DB is bound to its original repository path. Do not copy/merge DB files between repositories or branches.

```bash
python3 "$SKILL_DIR/scripts/columbus.py" sync --repo "$REPO"
python3 "$SKILL_DIR/scripts/columbus.py" sync --repo "$REPO" --verify-content
python3 "$SKILL_DIR/scripts/columbus.py" status --repo "$REPO" --verify-content
```

- `sync --summary`: fast refresh with counts, work metrics and freshness; omits file inventory and diagnostic text. Use plain `sync` or `status` for the full details.
- `sync --verify-content`: read/hash every included source and configuration input.
- `status`: read a saved snapshot; no refresh. With `--verify-content`, verify current source/config/Git state but do not rewrite the index.
- `search`, `symbol`, `neighbors`, `impact`, `context`, `graph`: sync before query by default. `--snapshot` explicitly opts out.
- Optional MCP `serve`: read-only tools; synchronize separately before reads and after changes. No read-only tool silently writes the index.

## What changes invalidate the graph

| Change | Current behavior |
|---|---|
| Ordinary dirty/untracked source | Enumerate and compare metadata; hash changed candidates, reparse changed content |
| Delete | Remove symbols/FTS rows and re-resolve graph from current cached facts |
| Rename | Treat as removal plus addition; regenerate path-based IDs |
| HEAD or branch change, including pull/merge effects | Force content hashing; reuse identical parse results where configuration is unchanged |
| Separate worktree | Use a separate default DB; reject a DB belonging to another root |
| Gradle/Maven/ignore/version-catalog input change | Change configuration fingerprint; conservatively reparse/relink |
| Analyzer code, actual grammar/runtime version, language set | Change analyzer fingerprint and rebuild relevant stored facts conservatively |
| Schema 2 or 3 database | Readable; next sync atomically rebuilds into compressed schema 4 |
| Schema 1 / unknown database schema | Refuse migration; choose a new DB path and rebuild |

Configuration filenames include `build.gradle`, `build.gradle.kts`, `settings.gradle`, `settings.gradle.kts`, `pom.xml`, `gradle.properties`, `gradle.lockfile`, `libs.versions.toml`, `.columbusignore`, and `.gitignore`. Their content is a freshness input, not an executed build or a resolved dependency graph. Configuration outside a restricted source root is still considered when discovered within the repository.

## Costs and consistency

Fast sync still enumerates/stats included files. Unchanged snapshots reuse persisted diagnostics and reference counts without loading parse bodies; `refresh.cached_parses_loaded` counts cached documents decoded when relinking. Metadata includes size, mtime, ctime, inode and device; it is an optimization under ordinary local filesystem behavior, not content proof. Known-extension no-op sync avoids reading source bodies. Unknown-extension text fallback probes contents and reports inventory.probe_files/probe_bytes. This implementation still performs global cached-fact relinking after graph changes. It does not promise work proportional only to changed files.

Source reads compare metadata before/open/after read. A final inventory/stat/Git check catches ordinary concurrent edits or branch switches; a failed check aborts the DB transaction and asks for retry. SQLite uses one writer and commits files, symbols, edges, FTS and metadata together. Readers retain an existing consistent DB snapshot. This is not a malicious-file-race sandbox or a filesystem-wide atomic snapshot.

Read the `freshness`, `last_sync_check`, `refresh`, `diagnostics`, `revision`, `git_state` and analyzer/config fingerprints. `metadata_checked` differs from `content_hash_verified`; snapshot-only query results remain labeled as snapshots. `read_symbol`/`context` verify selected original bytes before returning code. Parsing diagnostics can coexist with an otherwise successful DB generation; partial files must not be interpreted as complete call graphs.

No automatic retry loop runs forever. Retry a reported concurrent-change failure after the tree stabilizes. If parsing is partial, inspect diagnostics and source, fix the source or change the parser version deliberately, and sync. Do not clear errors or reuse stale success solely to return a result.

## Scope and exclusions

Default supported source extensions are `.kt`, `.kts`, `.java`, `.py`. Other source/document formats are not semantically analyzed. Git enumeration includes tracked and nonignored untracked files; `.gitignore` does not retroactively exclude tracked files. Without Git, use filesystem enumeration and the bundle's exclusion patterns, not a claimed complete gitignore implementation.

Exclude symlinks, `.git`, `.columbus`, environment/dependency caches, `.agents`, `.claude`, `.codex`, `.gradle`, `.idea`, `build`, `dist`, `target`, `out`, and `generated` directories. Source files above 1 MB are reported and excluded; selected config files have a 10 MB read cap. `.columbusignore` uses simple path/basename globs, not full gitignore negation semantics. Default sensitive filenames are only a convenience, not DLP.

Generated-code exclusion can omit declarations used by handwritten code. Report this gap rather than claiming all dependencies are present. No hooks/watchers are installed. Query-time checks are the current synchronization mechanism; watcher/queued-event optimization and compiler indexes remain later work.

`status --summary --verify-content` verifies source hashes and reports stale file/config counts and reasons without listing every path. `diagnostic_count` and `unresolved_references` remain visible; `semantic_complete=false` is separate from freshness. A summary never implies that excluded diagnostic details are empty. The API still returns full status; the CLI projection reduces delivery bytes only.

## Storage format

Schema 4 retains lossless zlib-compressed UTF-8 JSON parse facts in `files.parsed`; use the engine's decoder instead of treating this internal BLOB as plain JSON. Public search, graph and JSONL tree formats remain readable JSON. No runtime dependency is added. Search document bodies are also compressed behind an external-content FTS index; use engine connections to read that internal view. Schema 2 and 3 remain readable, but their first sync reparses all sources and atomically upgrades the cache; failure preserves the prior snapshot. Older engines reject schema 4, so use separate `--db` paths when comparing versions. Existing SQLite files can retain freed pages after migration; the smaller fresh-database size is not an automatic on-disk shrink.

SQLite retains freed pages after an in-place upgrade. A fresh `--db` gives the compact physical size; existing databases can reclaim free pages with SQLite `VACUUM` when no other operation is using the cache. Compression reduces stored parse facts, not the full-text index or graph rows. Source bytes, response bytes, sync latency, and model tokens remain separate measurements.

`refresh.discovery_probe_files` and `refresh.discovery_probe_bytes` total content probes across both discovery passes in a completed sync, including probes of excluded binary or unsupported-encoding files. Repeated reads count again. `inventory.probe_*` describes only the initial discovery pass. These are separate from `refresh.hashed_*`: zero hashed bytes in a metadata-checked sync does not imply zero content reads. Probe counters are application read volume, not physical disk I/O or a complete count of configuration/Git/metadata reads.
