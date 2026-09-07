# Issue #6: agent sync/status summary

2026-09-08 KST. Same current Spring snapshot, serialized CLI status output including final newline:

- Full: 99,580 UTF-8 bytes.
- `--summary`: 865 UTF-8 bytes (99.1% smaller).
- Revision, counts, freshness, references and diagnostic count match the detailed output.

`sync --summary` and `status --summary` omit file inventory and diagnostic text while preserving parse/hash/cache/relink work and coverage counters. `status --summary --verify-content` reports stale file/config counts and reasons. `details_omitted=true` makes omission explicit. The API still returns full metadata; this change reduces CLI delivery bytes, not index computation or measured model tokens.

Reproduce with `columbus status --repo /path/to/spring-core` and the same command with `--summary` after `sync`. Raw outputs are retained next to this report. The regression checks a repository with 81 files, a parse error, unknown calls, stale content and subsequent repair. The skill now uses `sync --summary` after edits. Full diagnostics remain available by omitting the flag.

The current runtime uses the original pinned Java grammar, not the experimental annotation patch. These measurements do not close issue #6 or prove actual model-token savings.

Validation: 186 engine and 49 root tests passed; compilation, skill quick_validate and diff checks passed locally. No hosted platform validation is claimed for this combined worktree.
