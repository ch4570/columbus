# Portable AST workflow validation

The same engine now provides AST processing, parent-first JSONL navigation, bounded source chunks, optional native Git hooks, and a pre-commit framework hook. See [workflow and installation](../../docs/portable-ast-workflow.md).

Local evidence on macOS arm64 / Python 3.11:

- `test_portable_ast.py`: six integration/contract tests covering real native commits with partial staging, linked worktrees, existing hook and core.hooksPath preservation, strict parse rollback, deletion-only refresh, AST/fallback separation, parent closure and partial diagnostics.
- [Clean distribution verification](results/distribution.json): wheel installation in an isolated environment, target directories containing spaces, native commits without PYTHONPATH, portable ZIP bootstrap, removal/relocation of the original ZIP source before running the installed hook, and JSONL tree lookup through both installation routes.
- [pre-commit framework verification](results/pre-commit.json): an isolated wheel install in the framework's own Python environment; the hook indexes staged source while the framework hides unstaged tracked edits; source is restored after commit; subsequent exploration updates to restored content; deletion-only commits remove old declarations. This local consumer uses a local hook entry with the built wheel as an additional dependency. The public manifest is validated separately, and the same scenario is included in all six CI matrix environments. A second [remote repository installation](results/remote-pre-commit.json) consumed the actual GitHub manifest at pinned commit `d45e09c9b35c5e52746cc723c2f2fd5a8dcf0bbc` in a fresh framework environment and passed the same commit/restoration/deletion checks.
- [spring-core AST tree](results/spring-resource-tree.jsonl): a five-node bounded view rooted at DefaultResourceLoader's file/class, parent IDs and verified-snapshot source hashes, explicit truncation and 16 repository diagnostics. The existing full spring-core corpus contains 1,091 Java and 34 Kotlin files plus resources. Default tree export excludes non-AST fallback nodes.

The checked-in distribution receipt was captured after the first successful portable implementation. Later changes adding fidelity counts to the hook summary are exercised by the final PR CI; receipt byte counts are not a final performance benchmark. No claim of compiler-equivalent call resolution is made; issue #8 remains open for known false targets.

Reproduce the framework integration from a built wheel:

```sh
python -m pip install pre-commit==4.6.2
python -m pre_commit validate-manifest .pre-commit-hooks.yaml
python scripts/verify_pre_commit.py --wheel dist/columbus-1.0.0-py3-none-any.whl
```

Use `scripts/verify_distribution.py --wheel ... --bundle ...` for the isolated wheel/ZIP consumer scenarios. Engine tests must run from `skills/columbus/scripts` as documented in CONTRIBUTING.md. Source-suite subprocesses share the checkout through PYTHONPATH; the clean distribution verifier explicitly removes it.
