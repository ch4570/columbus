# Issue #4: annotated Java varargs grammar evaluation

2026-09-08 KST. A grammar fix is implemented as a reproducible patch and verified locally. It is **experimental**, not the shipped runtime grammar. Platform/release integration remains unfinished.

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

Raw evidence: [summary](results/summary.json), [compiler output](results/compiler.json), [pinned parser](results/pinned.json), [upstream candidate](results/candidate.json), [local fix](results/fixed.json), [upstream suite](results/upstream-corpus.txt), [engine suite](results/engine.txt). Binary hashes distinguish the experimental builds, which retain upstream's package version in this evaluation. Runtime dependency pins and installed production environments were not changed. No Windows/Linux or Python 3.14 validation is claimed.

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

Remaining adoption work: package the patched grammar with a distinct version/provenance, build and test all supported Python/platform combinations, verify upgrade invalidation and clean wheel/ZIP installation, and rerun call-precision evaluation after partial-file suppression changes. The corpus and patch are ready for that work; issue #4 remains open until the shipped implementation meets those gates.
