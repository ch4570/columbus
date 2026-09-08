# Prospective reuse of byte-identical historical graphs

The three existing XZ graphs can be reused for this prospective saved-archive comparison without constructing another cold SQLite index. This choice is declared before the new cohort is frozen or any new model runs. The original producers, graph bytes, revisions, source scopes, exclusions and historical preparation costs remain identified; candidate `382d92a780e933f43e267d12f41869c816eee3bb` is the consumer runtime, not the producer of these artifacts. No historical input, answer, failure, score or retained artifact was changed by this review.

`graph-bindings.json` is a top-level `java`/`kotlin`/`javascript` mapping. Each language binds the exact graph `fixture`, SHA256, bytes, revision and footer counts; the complete source ZIP and source-manifest hash; actual producer commit; historical timings; frozen Git dependency references; complete producer-runtime inventory hash; and the independently checked candidate-code equivalence. Absolute paths identify existing local artifacts, not portable retrieval instructions.

## Bound artifacts

All paths below are relative to the existing `/tmp/columbus-source-call-sites.x1RWXz/` checkout. Full SHA256 values are machine-readable in the adjacent binding file.

| Task | Original graph path | XZ bytes | Preserved revision | Producer runtime commit |
| --- | --- | ---: | --- | --- |
| Java | `evals/quotes-three-arm/java/graph.jsonl.xz` | 3886556 | `cf482b13ebb638a175d9` | `402940994ba519a3a02a521ccfed55b73d310dbf` |
| Kotlin | `evals/quotes-three-arm/kotlin/graph.jsonl.xz` | 3886560 | `3352a120ff0a3ffe0b24` | `402940994ba519a3a02a521ccfed55b73d310dbf` |
| JavaScript | `evals/overload-token-cohort/retained/javascript/graph.jsonl.xz` | 219392 | `14898a983357327f60a7` | `588f2db846fff7036eff95a0d917277d225ae734` |

The JavaScript graph is under `retained/javascript/`, not directly under the historical language directory. Its retention manifest binds these exact bytes to `/tmp/columbus-overload-token-javascript/graph.jsonl.xz`.

Complete read-only streaming scans found one manifest and one footer per artifact. Actual record counts matched both each footer and the frozen engine record:

| Corpus/graph | Files | Nodes | Scopes | Edges | References | Imports | Diagnostics |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Spring Java and Kotlin, each | 1166 | 20811 | 20647 | 32145 | 68007 | 7723 | 16 |
| Axios JavaScript | 237 | 778 | 0 | 1270 | 7258 | 390 | 1 |

Both Spring compressed artifacts are deliberately preserved separately. After the first manifest line, their decompressed record bytes are identical, SHA256 `abf99328da91f541d352a6fe4ff2efeb0644c3f9a8f7dece011ad08c953577b8`. Their manifest revisions and compressed hashes differ. Reuse does not rewrite either revision or imply a fresh index at another root would reproduce it.

## Complete source scope, including graph exclusions

Every member of each new selected source ZIP was compared against the complete historical `manifest.source_manifest` and `engine.archive.source_manifest`: all 1166 Spring module files and all 242 Axios superproject files matched. The hashes are the same as `sources.json`. Every actual archived file record also matched its ZIP member's raw SHA256 and exact byte size, with no mismatches. Source ZIP/local snapshot full-inventory equality was independently checked during the accompanying source review.

Spring graph coverage includes all 1166 files of the scoped module. This remains the complete `spring-core` subtree, not the complete multi-module Spring repository.

Axios retains all 242 source files for every arm, but the historical graph indexes 237. The five omitted graph file records are disclosed, not removed from source scope:

- `.gitignore`: discovery configuration rather than an indexed source record.
- `package-lock.json`: 1825590 bytes, over the 1000000-byte limit; the graph retains the corresponding exclusion diagnostic.
- `test/unit/adapters/axios.png`: binary-extension exclusion.
- `test/unit/adapters/cert.pem` and `test/unit/adapters/key.pem`: secret-extension exclusions for public upstream test fixtures.

These classifications follow unchanged `discovery.py` constants and branches at lines 23–34 and 165–185. Do not call this graph complete coverage of every superproject file or infer semantic completeness from its complete serialization. Its JavaScript/TypeScript analyzer fidelity is heuristic; Spring Java/Kotlin fidelity is AST with the recorded diagnostics intact.

## Producer provenance and candidate equivalence

Spring preparation is preserved in frozen cohort commit `d4384adc0207a19c59025adc1decc91ab2a20a52`. Its `prepare.py` exports the quotes runtime from commit `4029409…`, executes sync and XZ snapshot export in the quotes observation, then copies the graph to the other arms. The old control runtime `9c0d3c3…` consumed the graph; it did not produce it. The original `quotes.engine` records bind all 37 runtime/skill/reference files. Their complete inventory matches both the retained `runtimes/quotes/` bytes and every corresponding Git blob at the producer commit.

Axios preparation is preserved in frozen cohort commit `c4ee65c25d40c8085ee659df1da67df651c66b74`. Its `prepare.py` calls `observe_saved_callers.freeze_archive`, which copies the runtime, runs sync, exports XZ and records the resulting graph hash/revision/counts. Before that cohort's freeze, `verify_runtime_commit` checks every copied runtime file against the recorded `environment.runtime_commit` `588f2db…`. All 36 frozen files match the retained shared runtime and producer Git blobs. The later retention manifest independently records the byte-identical archive copy and original graph path. The engine does not itself contain a runtime-commit field, so that commit must be attributed to the verified environment/preparation chain, not an invented engine field.

The relevant historical `prepare.py`, `common.py` where applicable, environment, language freeze and graph files were compared to their original frozen input hashes and frozen-commit Git blobs. The adjacent JSON records those dependency hashes and the post-run JavaScript retention manifest separately. This is preserved preparation-record and byte-binding evidence, not a new observed sync/export execution or an external cryptographic attestation of the original subprocesses.

Candidate equivalence was checked without importing or executing any target runtime:

- Spring producer versus candidate: every shared runtime file is byte-identical except `SKILL.md`, `columbus/cli.py`, `references/agent-context.md` and `references/archive.md`; candidate adds `columbus/source_calls.py`. The complete `archive.py`, parser, discovery, language profile, resolver/index and exporter bytes are identical.
- Axios producer versus candidate: the same reader/skill differences apply, and candidate adds `quotes.py` plus `source_calls.py`. Whole `archive.py` is **not** byte-identical: its only diff adds `_overload_receiver_hint` and adjusts `source_archive_many` ambiguity diagnostics. The archive-writing function and its compression/validation helpers are unchanged, as are all parser/discovery/index modules. CLI changes add reader options/branches and reader-specific error handling; sync/export command behavior is unchanged.
- The exact source bytes of `archive()` at physical lines 29–88 are identical across all three runtime commits: 3563 bytes, SHA256 `141606efc2b42aad2d4234468f869133133d0fdf665b4e95d3aea6a19272a2c9`. This was extracted with the standard-library AST's function coordinates and original `splitlines(keepends=True)` bytes, not by importing the module.
- Independently hashing candidate Git blobs in `languages.analyzer_fingerprint` order reproduced each stored analyzer-code value: `031e485d2283806bd0a9` for Spring, `6f9565d03255b71d9332` for Axios. The ordered modules are `parser.py`, `discovery.py`, `language_profiles.py`, `polyglot.py`, `languages.py`, `index.py`, plus `jvm.py` for Spring. Python AST version is recorded as 3.12.14; Spring additionally records tree-sitter 0.26.0, tree-sitter-java 0.23.5 and tree-sitter-kotlin 1.1.0.

Manifest hashes in this receipt mean SHA256 of UTF-8 `json.dumps(mapping, sort_keys=True, separators=(',', ':'))` with Python's default `ensure_ascii=True`; maps associate relative paths with raw-file SHA256. The complete maps remain in the hash-bound historical freeze records instead of being duplicated here. Candidate code equality is not permission to relabel an old graph as freshly produced by candidate.

## Historical cost, new preparation and remaining checks

| Task | Historical cold index seconds | Historical XZ export seconds |
| --- | ---: | ---: |
| Java | 8.18254083400825 | 3.9598633330024313 |
| Kotlin | 7.943478917004541 | 3.7136611249879934 |
| JavaScript | 1.14 | 0.313 |

These are the original engine measurements; the JavaScript observer rounded them to milliseconds. They are not newly measured candidate times. For the new cohort, record preparation as `historical_graph_reuse`; no new cold index/export was performed. A new cold-time field should be absent/null with that explanation, not a fabricated zero. Copying/verifying reused artifacts may have its own separately measured preparation cost. No model-token or effectiveness result follows from this disk-saving preparation choice.

Before a future freeze, preparation must validate the exact artifact hashes/counts/source manifest against these bindings, retain the original graph identity for each language, and give every arm that language's same graph bytes and full source ZIP. Export the separately pinned consumer runtimes normally and verify their inventories. Review the new operation's actual relationships and run its new positive/negative controls against both consumer runtimes. All frozen-input, full semantic/citation/execution, all-repetition and strict actual input AND output gates remain required; existing failures stay unchanged. The adapter still depends on authoritative common preflight, and only the new source/call receipt branch independently reconstructs maximal source/call pages—the legacy receipt rules are not generalized into that stronger claim.

This audit created only `GRAPH-REUSE.md` and `graph-bindings.json`. It ran no index/export, repository code, model, historical evaluation, network retrieval or source mutation.
