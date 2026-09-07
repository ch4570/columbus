# Polyglot navigation fixture

This repository-shaped fixture exercises TypeScript imports/calls, Go and Rust
functions, C++ local includes/calls, an extensionless Python script, a custom
workflow language, and unknown text fallback. It is static input, not a runnable
multi-service application.

From the RepoAtlas source checkout, after installing the CLI:

```sh
repoatlas map --repo examples/polyglot-demo --format text --budget-tokens 2000
repoatlas search checkout --repo examples/polyglot-demo --format text
repoatlas graph --repo examples/polyglot-demo --format mermaid --level file \
  --kinds imports calls --output .repoatlas/polyglot-dependencies.mmd
```

Every command targets the fixture explicitly. The first query creates its index;
the export creates a new output file and preserves an existing file at that path.

`.repoatlas.json` adds `.flow` as `workflow` and recognizes the literal `task`
declaration keyword. No repository code or custom plugin executes. The fixture
intentionally makes no cross-language runtime call claims.
