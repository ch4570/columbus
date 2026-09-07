# Changelog

This file describes source and bundle versions. A version entry does not imply publication to a package registry or a GitHub release.

## Unreleased

- Expose parent-first AST declaration trees as JSONL with labels, source hashes/spans, parse status and bounded node counts.
- Support an installable `columbus-sync` pre-commit hook and opt-in native Git hooks, preserving existing hook managers and staged source.
- Add compact visible-worktree refresh reporting and strict parse rollback; retain partial-parse evidence in bounded context and relationship responses.
- Verify wheel/ZIP portability, linked worktrees, framework stashing/restoration and deletion-only updates.

- Prevent native JVM indexing crashes on long source files by deriving line spans from UTF-8 byte offsets.
- Include Java annotation interfaces and their elements in declaration search and import graphs.
- Preserve exact symbol IDs in search and bounded context so long Java paths cannot displace the requested method.
- Add a reproducible [spring-core field evaluation](evals/spring-core/README.md), with raw timings, source checks, remaining graph gaps, and storage/response costs.

## 1.0.0 — Columbus · 2026-09-07

- Give the project the Columbus identity: a navigator character, repository `ch4570/columbus`, and matching English and Korean guides.
- Rename the package, import, command, and MCP server to `columbus`; distribute `get-columbus.py`, a wheel, and a source ZIP with checksums.
- Use `.agents/skills/columbus/`, `.columbus.json`, `.columbusignore`, and `.columbus/index-v1.sqlite`. Leave preview installations and caches intact, and exclude old runtime directories from new discovery.
- Publish reproducible Columbus response-delivery benchmarks and graphs, alongside clearly labeled historical actual-agent measurements. Retain the original observations, including regressions and excluded trials.
- Keep the checksum, ownership, source freshness, response budget, and release-version guards. Add regression coverage for renamed and archived engine loading.

**Breaking change:** the private RepoAtlas preview is not upgraded in place. Install Columbus as a new tool, copy any custom configuration to the new filename, install the new skill, and rebuild the index. [Migration guide](INSTALL.md#moving-from-the-repoatlas-preview).

## 0.5.0 — 2026-09-07

- Put measured CLI response reductions and all three real-agent comparisons directly in the English and Korean READMEs, including increased model usage and citation-quality limits.
- Add `explore [QUERY]` with readable text and a 2,000 estimated-token default, task-named sessions, and `stats NAME`.
- Show a useful getting-started guide when the CLI is called without arguments.
- Add a Python-only release installer with checksum verification, an isolated user runtime, and safe launcher updates.
- Distribute installable wheels, portable source ZIPs, the installer, and checksums in GitHub Releases. The automatic release workflow requires the platform test matrix; this private preview uses locally verified artifacts because hosted jobs could not start.

## 0.4.0 — Earlier local bundle

- Add compact text output for map, search, context, symbol, neighbors, and impact queries while retaining JSON as the default.
- Add opt-in context receipts to avoid repeatedly delivering already-seen source ranges.
- Add opt-in local retrieval telemetry and a summary command for inspecting response volume and deduplication.
- Center excerpts inside long functions and classes on the query while retaining exact-name headers; continue unread ranges with receipts.
- Validate both raw source and normalized decoded-source hashes before reusing receipt ranges.
- Discover an explicitly selected directory ignored by an enclosing Git repository instead of returning an empty index; keep normal Git-root ignore behavior.
- Present installation, language coverage, agent workflows, and measurement limits in English and Korean overviews with focused guides.
- Add reproducible efficiency observations, repository contribution/reporting templates, and updated distribution verification.

See [validation evidence](VALIDATION.md) and [token-efficiency observations](docs/token-efficiency.md) for executed checks and measurement scope.

## 0.3.0 — Earlier local bundle

- Expand the JVM-focused skill into a portable polyglot CLI, installable skill, and optional MCP server.
- Detect source and text using language profiles, conventional filenames, shebangs, and repository configuration.
- Export JSON, Mermaid, GraphML, and self-contained HTML graphs with scope and relationship filters.
- Add bounded maps and context retrieval, incremental synchronization, wheel/ZIP packaging, and offline wheelhouse installation.

That historical version used `repoatlas-jvm` and `jvm-v2.sqlite` as compatibility paths. Columbus 1.0 uses the new paths above.
