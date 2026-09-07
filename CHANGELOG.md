# Changelog

This file describes source and bundle versions. A version entry does not imply publication to a package registry or a GitHub release.

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

The `repoatlas-jvm` skill identifier and `jvm-v2.sqlite` cache filename remain as compatibility paths.
