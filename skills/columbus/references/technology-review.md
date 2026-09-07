# Graphify and related technology review

Checked 2026-09-07 against upstream docs and selected source; no upstream accuracy/cost benchmark reproduced. The user's “grapify” was interpreted as Graphify; revisit if a different URL is supplied.

| Project | Kotlin/Java and sync findings | Adoption decision |
|---|---|---|
| [Graphify](https://github.com/Graphify-Labs/graphify) | Local AST engine plus project-installed skills; Kotlin alias/package extraction. Current v8 is Apache-2.0 with earlier MIT contributions retained in [NOTICE](https://github.com/Graphify-Labs/graphify/blob/v8/NOTICE). | Reference the small entrypoint, deterministic scripts, project scope, and explicit version alignment. No code copied. |
| [GitNexus](https://github.com/abhigyanpatwari/GitNexus) | Docs list Java/Kotlin and serialized watch/incremental updates. [LICENSE](https://github.com/abhigyanpatwari/GitNexus/blob/main/LICENSE) is PolyForm Noncommercial 1.0.0. | Compare behavior; do not treat as permissively licensed commercial OSS. |
| [Code-Graph-RAG](https://github.com/vitali87/code-graph-rag) | MIT. [Language table](https://github.com/vitali87/code-graph-rag/blob/main/docs/architecture/language-support.md) distinguishes Java from Kotlin structural extraction without CALLS resolution. | Do not assume its Kotlin extraction meets this user's call-graph requirements. |
| [Serena](https://github.com/oraios/serena) | MIT LSP symbol/reference tools with Java/Kotlin support; capabilities depend on server. Separate JetBrains integration is not automatically part of the free core. | Live semantic-query complement to a stored graph. |
| [scip-java](https://github.com/scip-code/scip-java) | Apache-2.0 Java/Kotlin indexer; Kotlin integration less mature, compilation has build effects. | Planned opt-in compiler evidence, not connected in 0.2. |
| [Tree-sitter](https://github.com/tree-sitter/tree-sitter) | MIT syntax core, grammars separately versioned; incremental parsing is not incremental graph resolution. | Actual lightweight JVM syntax layer. |

## Graphify details

Graphify documents project installation and separate CLI/skill version alignment. Its flow distinguishes commit/checkout hooks from explicit update after pull/merge. Do not turn this into a claim of universal automatic synchronization. [Workflow](https://github.com/Graphify-Labs/graphify).

In v8 [watch.py](https://github.com/Graphify-Labs/graphify/blob/v8/graphify/watch.py), changed paths drive replacement/deletion and unchanged AST facts provide resolver context. Pending changes and locking handle overlapping events. Some paths rebuild the entire corpus; failed extraction remains eligible for retry. Re-parsing changed files alone therefore does not establish graph correctness.

This bundle separates bundle/code versions, synchronizes before CLI queries, fingerprints content/configuration, commits one successful DB transaction, and labels inferred calls. Skill installation and indexing install no hooks/watcher. The source-development `hook-install` command explicitly installs an optional native pre-commit hook while preserving existing hook managers; the `columbus-sync` manifest supports the pre-commit framework. These accelerate updates but do not replace query-time freshness checks.

## Evaluation

Use identical Kotlin/Java revisions and tasks to compare symbol/reference correctness, task completion, model input/output/cache usage, cold index, warm/change sync, and recovery. Include branches, dirty/untracked files, deletion/rename, build config, and worktrees. Compare incremental state to a clean rebuild. Never repeat upstream token-saving percentages as this bundle's result.
