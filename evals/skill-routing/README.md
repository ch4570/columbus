# Smaller skill entrypoint after actual-token regression

2026-09-08 KST. The previous six-trial [model observation](../exploration/results/current-skill/REPORT.md) loaded the full skill on small literal/code-location tasks; no graph tool was invoked, and both quality-passing pairs increased cumulative input. This change reduces avoidable instruction loading without claiming that this alone fixes measured model usage.

The entrypoint decreased from **7,227 to 2,966 UTF-8 bytes (58.96%)**. Its description now distinguishes graph-backed structure/dependency/archive operations from a known-literal/file lookup that needs ordinary search only. Implicit invocation remains enabled; explicit user skill requests remain supported.

Progressive retrieval, bounded source commands, sessions/context-loss boundaries, source freshness, semantic uncertainty and untrusted-content handling remain in the entrypoint. Session/receipt/telemetry details already live in agent-context.md. Installation, visual exports and MCP instructions moved to operations.md. Archive and AST/hook instructions remain linked to their existing references. The reference index now exposes these topics and evidence principles. The stale principle that always required a map before source was corrected to match the direct-search route.

Validation: skill quick_validate passed; every entrypoint/routing link resolves; a fresh `columbus init` installation has identical entrypoint bytes, all 43 managed-file hashes match, and installed routing links resolve. Root installation/distribution unit tests: 49 passed. [Installation receipt and hashes](results/installation.json).

This is a measured instruction-byte reduction, **not a new model-token result**. The previous unfavorable cohort remains unchanged. Reference loading, command count, caching and model behavior can offset the smaller entrypoint. A future predeclared task-quality/usage cohort is still required. Runtime graph semantics and release pins did not change in this revision.
