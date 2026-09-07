# Batched direct-caller evidence

`columbus callers NAME_OR_ID --budget-bytes 12000` returns incoming direct-call identities and one short, hash-verified source range per caller in a single compact JSON response. Unique names work directly; ambiguous names require a complete ID. Multiple call sites in one caller are counted, not duplicated. Use `neighbors` for all individual edges.

The packet preserves confidence labels, caller/target partial status, repository diagnostic/unresolved counts, revision, matched caller count and output truncation. Semantic completeness remains false. Source is read stably and matched against indexed hashes before excerpts are returned; changed source fails rather than pairing stale graph locations with new text. Whole-file source reads are cached within the query. JSON whitespace expansion is rejected to preserve the serialized byte budget.

On the independently reviewed c67b20a fixture, the [4,327-byte packet](packet.json) contains all seven expected callers and a reviewed call location for each, with no truncation. This replaces graph traversal plus separate source-range requests for this task; it is not yet an actual-model token-saving measurement. Each excerpt is short and may not contain a complete multiline expression. Call counts and the packet do not establish runtime dispatch or graph completeness.

Regression tests cover nested lexical ownership, exact caller sets, confidence/hash presence, Unicode byte-budget truncation, changed-source rejection and ambiguous names. A future predeclared paired model run must verify both answer quality and total tokens.

Validation: all **194 engine tests** passed. Direct CLI checks confirmed a 1,024-byte response ceiling and rejection of `--pretty`; skill quick-validation passed. Full clean-distribution and hosted matrix validation for this new command are still pending.
