# Prelaunch checkpoint

Status: incomplete preparation. No model has been launched. This document is
not an approval to execute and must be completed before `prepare.py freeze`.

The per-language `source.json` files are byte-identical retained historical
provenance receipts: Java/Kotlin from `evals/quotes-three-arm`, JavaScript from
`evals/overload-token-cohort`, at development commit `fac1a25fab18463959ba725fc288b1067f4b9861`.
Their old task-specific review/relationship fields are historical metadata, not
this cohort's rubric or accepted relationships. This cohort uses its own
`cases.json`, `criteria.json`, `SOURCE-REVIEW.md` and eventual `relationships.json`.
The standalone Apache-2.0 license is also retained byte-identically; no old file
is edited or regraded by these copies.

## Required before freeze

- Review the exact candidate/control package delta and tested/merged tree proof.
- Validate every source ZIP's complete file map, pin, corpus boundary and license.
- Read all task descriptions, semantic clauses and cited implementation/test code.
- Explicitly retain Java/Kotlin historical-operation overlap and edge-selection bias.
- Pass the new protocol, collector, control and independent source/call evidence tests.
- Prepare fresh observations with identical source/graph bytes and isolated runtime exports.
- Review exact saved relationship tuples against source; reject unrelated or fabricated dispatch.
- Capture actual positive/negative control commands and preserve every original result.
- Replay all controls, source/runtime/graph inventories, environment and balanced schedules.
- Check at least 384 MiB free before preparation and 256 MiB afterward, at freeze and each launch.
- Freeze every input and used dependency, commit and push that prospective state.

## Candidate development verification

PR #21 head `382d92a780e933f43e267d12f41869c816eee3bb` passed all 12 native CI
checks (runs 34269624111 and 34269619006). The combined tree
`9363dafd73ec83dc72886ba19ded44d733ec74cd` was merged into the development branch
as `fac1a25fab18463959ba725fc288b1067f4b9861`, and its merged tree is identical.
The package export stays pinned to the tested head, not a moving branch.

PR #18's preserved 18-run study also passed 12 native CI checks, then merged as
`3840399d72416eea675aa3d57129e85fb222ebe8` with tested/merged tree
`f65612d2110328bd001aa6ef9dd36c1b33ec1b3b`. Its cost gates remain rejected: 0/6
primary and 0/6 secondary. No previous result is being replaced or regraded.

PR #12 remains open against main; no tag or release is authorized by this checkpoint.

## Model-free draft verification — 2026-09-08 20:11 UTC

All 64 new tests passed together locally: 19 protocol, 17 collector, 6 control
retention/replay and 22 independent source/call evidence tests. Tests include real
copied-runtime CLI deliveries in gzip/XZ and JSON/text, plus pure subprocess stubs
for the model runner. No actual cohort preparation, runtime export, index build,
control capture, freeze or model execution has occurred.

Cross-review found two issues before any cohort launch: a control timeout/decode
failure could lack an attempt marker, and deeply nested model JSON could escape
collector error handling. Both were fixed with regression coverage. Historical
runtime/recognizer/evaluation files remain byte-identical; only new cohort files
and its new independent evidence module/tests are added.

The final merged development commit `fac1a25fab18463959ba725fc288b1067f4b9861`
also passed all 12 post-merge native checks (34271204879 and 34271199500).
This is functional/integrity verification, not actual-model token evidence.

## Model-free prepared draft — 2026-09-08 20:39 UTC

All 96 focused tests passed together locally, including 16 new historical-graph
reuse tests; the unchanged candidate engine suite passed all 350 tests. The
runner regressions preserve malformed raw answers/events, complete the fixed
six-slot schedule for model-data errors, and still abort on real I/O/integrity
failures. Copy tests compare actual destinations against hashes of pinned Git
payloads, not newly adopted destination inventories. Retained runtime, graph,
source and producer receipts are checked against prepared arm records at freeze.

Read-only validation passed for all three original graph/source/provenance
bindings. The first actual model-free preparation then completed successfully at
`/tmp/columbus-source-call-observations.Jf0Jla/observations`. All nine consumer
preflights passed: Java/Kotlin each retain 1166 source and indexed files; JavaScript
retains all 242 source files and the historical graph's 237 indexed files.
No index or export command was executed. Historical producer times and new
copy/verification wall times are separately labeled in the prepared receipts.

All 15 citation positives and their corrupt-quote negatives passed. Independent
source/graph review bound 19 Java, 8 downstream-Java Kotlin, and 22 JavaScript
relationship tuples; each exact tuple and its physical source line were also
cross-checked by the integrating reviewer. `RELATIONSHIP-REVIEW.md` explicitly
records scope exclusions, missing calls and static-resolution limitations.

Actual JSON/text command controls are now being captured once, with original
attempt and raw-byte receipts. They are not yet declared passed in this draft.
Input freeze, committed/pushed freeze proof and native CI remain outstanding.
No model has been launched. The historical 0/6 primary and 0/6 secondary results
remain unchanged and no actual-model savings claim is made.

## First native CI and pre-freeze corrections

Initial head `129da366bf1dcaf2b848d43cc8b2637064938b74` failed native CI
(PR run 34276269017; push run 34276190645). All six PR jobs were inspected.
Python 3.11 rejected the deep JSON in decoding, while the test wrongly demanded
a serialization-error note. Python 3.14 successfully supported the tested deep
payload, invalidating that assumed failure and a second recursion/no-file test.
These are retained test failures, not successful checks or model outcomes.

Only protocol tests changed for that issue. A real bounded nested payload now
checks the actual supported outcome or truthful failure stage; deterministic
injected recursion errors check no-file and post-decode fallback contracts.
Real lone-surrogate, cyclic and nonfinite inputs remain covered, as do all raw
bytes, terminal/hash/preflight checks, fixed six slots and hard I/O failures.
The corrected protocol tests passed locally on Python 3.11 (37 tests).
Post-fix native checks remain required; no old CI run is retried or erased.

Separately, the prospective adapter avoids a full source/call snapshot when no
command could use that format. `CONTROL-CAPTURE.md` records the original in-memory
capture version, offline profiling, receipt-parity checks and the explicit common
pre/postflight dependency. All eligible candidates retain full original checks;
the standalone recognizer is unchanged. This is not a model-token saving claim.
