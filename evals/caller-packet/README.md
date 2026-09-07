# Batched direct-caller evidence

`columbus callers NAME_OR_ID --budget-bytes 12000` returns incoming direct-call identities and one short, hash-verified source range per caller in a single compact JSON response. Unique names work directly; ambiguous names require a complete ID. Multiple call sites in one caller are counted, not duplicated. Use `neighbors` for all individual edges.

The packet preserves confidence labels, caller/target partial status, repository diagnostic/unresolved counts, revision, matched caller count and output truncation. Semantic completeness remains false. Source is read stably and matched against indexed hashes before excerpts are returned; changed source fails rather than pairing stale graph locations with new text. Whole-file source reads are cached within the query. JSON whitespace expansion is rejected to preserve the serialized byte budget.

On the independently reviewed c67b20a fixture, the [4,327-byte packet](packet.json) contains all seven expected callers and a reviewed call location for each, with no truncation. This replaces graph traversal plus separate source-range requests for this task; it is not yet an actual-model token-saving measurement. Each excerpt is short and may not contain a complete multiline expression. Call counts and the packet do not establish runtime dispatch or graph completeness.

Regression tests cover nested lexical ownership, exact caller sets, confidence/hash presence, Unicode byte-budget truncation, changed-source rejection and ambiguous names. A future predeclared paired model run must verify both answer quality and total tokens.

Validation: all **194 engine tests** passed. Direct CLI checks confirmed a 1,024-byte response ceiling and rejection of `--pretty`; skill quick-validation passed. Full clean-distribution and hosted matrix validation for this new command are still pending.

## Clean installation follow-up

The distribution verifier now exercises `callers` after both wheel installation and ZIP bootstrap/source relocation. It checks nested lexical ownership, the exact caller set, source hash and confidence, compact 1,024-byte output, and rejection after modifying the indexed source. The source is restored and resynchronized after the negative check. The [local distribution receipt](distribution.json) confirms both paths passed on macOS arm64 / Python 3.11, alongside archive, installed-skill, session and hook checks. Root bootstrap/distribution unit tests also pass (49). Hosted matrix coverage for this extension remains pending.

## Hosted matrix

At commit `b4528c4`, all six ordinary distribution jobs passed ([run](https://github.com/ch4570/columbus/actions/runs/34142711192), [receipt](platform/final.json)). All six experimental Java grammar jobs also passed ([run](https://github.com/ch4570/columbus/actions/runs/34142722041), [receipt](platform/candidate.json)), including candidate upgrade/downgrade and clean wheel/relocated-ZIP caller checks ([installation receipts](platform/candidate-installations.json)). Matrix: Ubuntu/macOS/Windows × Python 3.11/3.14.

The initial ordinary run failed on Windows because the Unicode regression fixture was written using the OS default encoding, while Python source without an encoding declaration requires UTF-8. Explicit UTF-8 fixture reads/writes fixed the test; parser behavior was unchanged. The [initial failure receipt](platform/initial.json) is retained. Hosted tests remain scoped evidence; passing distributions do not prove model-token savings.

The [actual packet model comparison](../exploration/results/caller-packet/REPORT.md) passed both answer-quality gates but increased total input tokens 80.81%; the agent reread supplied citations in separate shell calls. That regression remains an active goal gap.
