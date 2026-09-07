# Issue #4: annotated Java varargs grammar evaluation

2026-09-08 KST. A grammar fix is implemented as a reproducible patch and verified as experimental wheels on six hosted platform/Python combinations. It is **experimental**, not the shipped runtime grammar. Platform/release integration remains unfinished.

The pinned tree-sitter-java 0.23.5 rejects legal annotations before `...` and accepts the invalid after-ellipsis placement. [Upstream issue #205](https://github.com/tree-sitter/tree-sitter-java/issues/205) and [PR #206](https://github.com/tree-sitter/tree-sitter-java/pull/206) describe the defect. PR #206 remains open at the time of this observation; its commit `6018d681d319aada6d9fe1b8a8d17f9f4d6c758e` changes grammar.js but does not regenerate parser.c. Installing that Git revision without regeneration therefore does not apply the grammar change.

| Source parameter | javac 17 | Pinned grammar | Upstream PR generated | PR + local patch |
| --- | --- | --- | --- | --- |
| `int @A ... values` | valid | partial | complete | complete |
| `int @A [] @B ... values` | valid | partial | partial | complete |
| `@A Class<?> @B ... values` | valid | partial | complete | complete |
| `int ... @A values` | invalid | complete | partial | partial |

The upstream candidate still commits to an array-dimensions continuation before it can distinguish the next dimension annotation from a varargs annotation. [dimensions.patch](dimensions.patch) replaces this forced associativity with an explicit dimensions conflict, allowing the parser to retain the alternatives. This changes the grammar; source bytes and annotations are never stripped, relocated or rewritten. Annotation byte spans and extracted parameter types were checked against the original valid fixtures.

All three grammars parsed the same 1,091 Spring Java files at commit `4c8c6409a27a62ab163d3b6196ad862b7c835440`. Source SHA-256 inventories matched. Partial files decreased from **5 to 0** with either generated candidate. Symbol/reference extraction totals remained **20,416 / 67,088**. Partial-file suppression in the resolver may therefore be lifted by the candidate, but this observation does not measure the precision of those newly eligible edges. Python, Kotlin, resources and runtime dispatch are outside this Java-only corpus count.

The five repaired files are ClassUtils, MethodInvoker, ObjectUtils, ReflectionUtils and ResolvableType. No assertion of compiler-equivalent parsing is made for every Java feature.

Validation on macOS arm64 / Python 3.11:

- Compiler oracle: three legal forms compile; the invalid placement fails. Annotation definitions are separate files, so fixture source bytes remain identical.
- Generated grammar: 110/110 upstream corpus parses and 17 syntax-highlighting assertions passed.
- Columbus engine: 185 tests passed with an explicit assertion that the patched grammar module was loaded.
- Local fixture spans, parameter types, corpus hashes and Python compilation passed.

Raw evidence: [summary](results/summary.json), [compiler output](results/compiler.json), [pinned parser](results/pinned.json), [upstream candidate](results/candidate.json), [local fix](results/fixed.json), [upstream suite](results/upstream-corpus.txt), [engine suite](results/engine.txt). Binary hashes distinguish the experimental builds, which retain upstream's package version in this evaluation. Runtime dependency pins and installed production environments were not changed. The original observations above were local; the later candidate wheel matrix below adds Windows/Linux and Python 3.14 evidence.

## Reproduce

Run from the Columbus repository root with its development environment installed. Use a fresh temporary directory for the grammar checkout and target installation. Capture the pinned observation before changing PYTHONPATH:

```sh
.venv/bin/python evals/java-grammar/observe.py /path/to/spring-core /tmp/pinned.json
.venv/bin/python evals/java-grammar/verify_compiler.py /path/to/jdk/bin

git clone https://github.com/tree-sitter/tree-sitter-java.git /tmp/java-grammar
git -C /tmp/java-grammar fetch origin pull/206/head
git -C /tmp/java-grammar checkout 6018d681d319aada6d9fe1b8a8d17f9f4d6c758e
git -C /tmp/java-grammar apply "$PWD/evals/java-grammar/dimensions.patch"
(cd /tmp/java-grammar && npx --yes tree-sitter-cli@0.27.0 generate --abi 14 && npx --yes tree-sitter-cli@0.27.0 test)
.venv/bin/python -m pip wheel --no-deps --wheel-dir /tmp/java-wheels /tmp/java-grammar
.venv/bin/python -m pip install --no-deps --target /tmp/java-fixed /tmp/java-wheels/*.whl
PYTHONPATH=/tmp/java-fixed:skills/columbus/scripts .venv/bin/python evals/java-grammar/observe.py /path/to/spring-core /tmp/fixed.json
```

Omit the local patch step to reproduce the upstream-only candidate. The shell example is POSIX; it does not substitute for supported-platform validation. Generation requires Node and a C build toolchain. The unmodified upstream license is retained in [UPSTREAM-LICENSE](UPSTREAM-LICENSE).

Remaining adoption work: integrate the candidate into the shipped dependency and clean Columbus wheel/ZIP installation path, extend the local upgrade probe to the hosted release path, and rerun call-precision evaluation after partial-file suppression changes. The corpus and patch are ready for that work; issue #4 remains open until the shipped implementation meets those gates.

## Candidate wheel matrix

`.github/workflows/java-grammar-candidate.yml` now builds the pinned upstream revision plus the local patch independently on Ubuntu, macOS and Windows with Python 3.11 and 3.14. `package_candidate.py` assigns the experimental local version `0.23.5+columbus.1` and records generated parser, binding, license and patch hashes. `verify_candidate.py` requires that exact installed version, hashes the native binary, and checks valid/invalid annotation parsing and original annotation spans before running the engine suite. Each job retains its wheel and receipts as an artifact. These are experimental artifacts, not release dependencies.

A local macOS arm64 / Python 3.11 wheel build, target installation and fixture verification passed. Hosted run [34138003324](https://github.com/ch4570/columbus/actions/runs/34138003324), at commit `56350ec`, passed **all six combinations**. Each completed upstream grammar checks and the current engine regression suite after installing the candidate wheel. All six generated `src/parser.c` hashes match. [Run receipt](results/platform-matrix/final.json) and [wheel/source/runtime hashes](results/platform-matrix/artifacts.json) retain the evidence. The initial run failed to fetch an unmerged commit through ordinary clone; explicitly fetching its pinned SHA fixed that setup failure, preserved in [initial receipt](results/platform-matrix/initial.json). This matrix does not yet prove clean Columbus bundle adoption, upgrade invalidation, or newly enabled call-edge precision.

The local upgrade probe (`verify_upgrade.py`) uses fresh processes and an actual separately installed candidate package. With unchanged source, pinned → candidate → warm candidate → pinned yielded parsed-file counts **1 → 1 → 0 → 1**, and partial flags **true → false → false → true**. The existing package-version fingerprint invalidates the cache on both upgrade and downgrade. This is local fixture evidence, not a full release upgrade test. See [receipt](results/package-upgrade.json). The local candidate also passed all **190** current engine tests and the **14** javac-backed literal/varargs guard cases; package and guard receipts are in [package-local](results/package-local).

## Columbus installation integration

The candidate is supplied through the existing `--wheelhouse` option. A real clean-install probe exposed that `doctor` used exact string equality even though pip's public `==0.23.5` pin accepts a local build such as `0.23.5+columbus.1`. The readiness check now compares the public version, while preserving the full installed version in diagnostics and cache fingerprints. Other releases and prereleases remain rejected; the engine regression suite now has 191 tests.

The local macOS arm64 / Python 3.11 run passed clean Columbus wheel installation, the standalone installer, and ZIP bootstrap after moving the extracted source. All three environments were required to load exactly `0.23.5+columbus.1` and pass four annotation grammar cases. Existing graph/archive, installed-skill, session, and hook checks also passed. See [local installation receipt](results/package-local/distribution.json). The candidate workflow now adds these clean-install checks and the actual package upgrade/downgrade probe to every hosted combination; all six combinations passed in [run 34138741132](https://github.com/ch4570/columbus/actions/runs/34138741132) at `daa7b60`. Each has three successful candidate installation probes and upgrade/downgrade parsed-file counts 1 → 1 → 0 → 1. [Run receipt](results/installation-matrix/run.json) and [all installation/upgrade/wheel receipts](results/installation-matrix/receipts.json) preserve the evidence. The ordinary pinned-runtime distribution matrix also passed all six jobs at the same commit ([receipt](results/installation-matrix/production-run.json)).

This does not make the candidate the default public dependency. Production installation without a candidate wheelhouse still selects upstream 0.23.5. Publishing or bundling candidate wheels, release upgrade evidence, and newly eligible call-edge precision remain adoption gates.

A further compiler check covers 12 calls newly eligible after annotated primitive varargs parse successfully: six valid literal/empty/null-array cases retain a target and six invalid literal cases remain unresolved. All match javac 17. The exact sources, hashes, compiler diagnostics and graph references are in [annotated call evidence](results/package-local/annotated-calls.json); rerun `verify_call_precision.py` with the candidate on `PYTHONPATH`, a JDK bin directory, and an output JSON path. This narrow probe does not establish reference/array applicability or precision of every newly enabled Spring edge.

Existing bootstrap installations now detect changed explicit wheelhouse bytes and upgrade to candidate builds; a real unchanged-source probe confirms adoption and a warm no-pip rerun. See [bootstrap adoption report](results/bootstrap-upgrade/REPORT.md). This does not make the candidate a default release dependency.

Candidate ZIPs can now embed parser wheels and use them by default without a user wheelhouse argument. Local clean-install, upgrade/relocation and no-fallback probes pass; see [bundled-default report](results/bundled-default/REPORT.md). Public release aggregation and ordinary wheel/standalone defaults remain unfinished.
