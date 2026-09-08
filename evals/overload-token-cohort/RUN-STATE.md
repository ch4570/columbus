# Actual run handles (mutable status, not protocol)

Protocol commit: `c4ee65c25d40c8085ee659df1da67df651c66b74`.
Frozen runtime commit: `588f2db846fff7036eff95a0d917277d225ae734`.
Input manifest: 108 files; SHA-256 `f6394e9832690454024cf21728f10cba5933623f12ae3858f52dfb842f49914c`.

The three fixed task groups launched at approximately 2026-09-08 16:02:35 UTC. Root execution sessions: Java `97841`, Kotlin `93576`, JavaScript `68234`. Each group has four sequential trials as predeclared. Observe these same handles until terminal; do not restart a group because results are absent. Original OS process identities/timestamps are under each observation's runner/process files.

Observation roots: `/tmp/columbus-overload-token-java`, `/tmp/columbus-overload-token-kotlin`, `/tmp/columbus-overload-token-javascript`.

At launch, source/archive/control checks and 23 new gate/protocol tests passed. Full local suites: 290 engine, 81 root, 29 exploration, 3 continuous-session tests passed. Pip check and Python compilation passed. Protocol inputs will not be edited after launch. Semantic reviews and terminal evidence are separate later outputs.

## 2026-09-08 16:20 UTC checkpoint

Eight of twelve trials are terminal: Java baseline1/Columbus1, Kotlin Columbus1/baseline1/baseline2, JavaScript baseline1/Columbus1/Columbus2. All three original runner sessions remain active; do not restart them. Java is on Columbus2, Kotlin on Columbus2, JavaScript on baseline2. Java baseline2 is still scheduled after Columbus2. No timeout or process failure has occurred. Every first-repeat pair fails the strict output-reduction requirement; Kotlin also increases total input. Citation failures remain separate and preserved.

Independent semantic reviewers: root handles Java; Curie handles JavaScript; Franklin handles Kotlin repeat1; Nash handles Kotlin baseline2. Reviews are new artifacts under each language's semantic/ directory, never edits to frozen criteria.

`retain.py` is a new postprocessor, NOT executed yet. Run it only after all three actual handles report terminal, using `--terminal-confirmed`. It requires all twelve results and verifies all frozen inputs/events before writing a fresh retained/ tree. Current generated results/REPORT are intermediate and must be recollected after every semantic review is complete.

Frozen protocol push CI run `34248667309` passed all six platform jobs. Additional multilingual release verification passed 21 cases at `/tmp/columbus-overload-validation.yOwvoW/multilang.json`.

Separate future code: worktree `/tmp/columbus-receiver-guidance.E1uAsW`, branch `feat/receiver-routing-guidance`, commit `c4d7c9a11e86d8325c9b1cb7101c457c145d2e7c`, PR https://github.com/ch4570/columbus/pull/15 targets development only. It changes receiver-conflict error/help, not grouping, and passes 294 engine tests including 41 archive tests. This code has NOT touched the running cohort. PR CI `34250076665`, push CI `34250072493` are live; wait for the exact head's twelve checks before merge. Main/release PR #12 remains open and gated.

## Terminal checkpoint, 2026-09-08 16:35 UTC

All twelve executions finished without retries/timeouts. Original runner sessions are now terminal: Java `97841` exit0 confirmed at 16:30:52, Kotlin `93576` exit0 at 16:24:12, JavaScript `68234` exit0 at 16:22:15 UTC. Do not poll or relaunch these completed sessions.

Retention ran once after terminal confirmation and succeeded: 135 payload files, twelve exact gzip event streams, three exact archives and 36 shared runtime files. RETENTION.json SHA-256 `2bcd242876ec7d40d5e185b17a50d28141d9c9f35bfa55cd90961f9d567f7452`. Independent verification matched every retained byte/hash and original artifact set. No token pair reduces both input and output. Aggregate input/output increases are descriptive, not a replacement gate; see ANALYSIS.md.

PR #15 merged at `a4271c21b134fca042c17f9f2c659352382f3e39` after all twelve exact-head checks passed. Its merge tree equals tested head c4d7c9a. Merge CI runs `34250873937` and `34250869188` also passed all twelve jobs. The current evaluation branch still retains its original frozen runtime; no source/skill/protocol file changed during measurement. Reproduce this historical cohort from its pre-merge evaluation branch, not a newer development tree with changed runtime hashes.

## Final review checkpoint, 2026-09-08 16:40 UTC

All twelve semantic and execution-boundary reviews are complete. The final collector verifies 108 frozen inputs and twelve terminal trials, with no integrity errors or pending reviews. Its exit code 1 is the expected failed acceptance gate: 0/6 pairs accepted. An independent read-only collector invocation reaches the same result and verifies every answer/rubric/events hash binding against retained bytes. All twelve execution-boundary reviews pass; citation and semantic failures remain separate and unchanged.

Final local checks include 81 root tests after completion, the previously passing 290 observed-runtime engine / 29 exploration / three continuous-session tests, 21/21 multilingual contracts, compilation, dependency consistency and diff whitespace. No additional model run or retention run was launched.
