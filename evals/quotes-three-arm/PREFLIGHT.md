# Prelaunch validation

Prepared and checked on 2026-09-08 UTC before any three-arm model launch. These are model-free checks, not actual-token or semantic-quality results. Runtime/skill exports and canonical source corpora are retained here; the observation root is recorded in environment.json.

## Exact inputs

- Control: 36 runtime/skill/reference files exported byte-for-byte from `9c0d3c3a54022237d32b9790ba4c1e0b2a758124`.
- Quotes: 37 files exported byte-for-byte from `402940994ba519a3a02a521ccfed55b73d310dbf`.
- The only export differences are `SKILL.md`, `references/archive.md`, `columbus/cli.py` and added `columbus/quotes.py`. Analyzer bytes are identical. Independent recomputation matches archived analyzer fingerprints: JVM `031e485d2283806bd0a9`, JavaScript `6f9565d03255b71d9332`.
- Actual read-only absolute-wrapper import diagnostics resolve every imported Columbus module to the frozen runtime, not the shared virtual environment's editable package. The control help lacks archive-quotes; the quotes help includes it. The cold producer uses the same absolute quotes wrapper.
- All nine arm source/runtime manifests match; each task's three archives are byte-identical to its retained archive. No consumer SQLite directory remains. The temporary producer index was removed only from each fresh, agent-created quote observation after export; the source and retained graph are preserved.
- Full source ZIP inventories, pins, scope and hashes are recorded in sources.json and independent language reviews. Spring has 1,166 source/indexed files per task; Express has 213 source files, of which 211 are indexed. Index coverage is not a claim that every semantic relationship is resolved.

| Task | Retained graph SHA-256 | Bytes | Cold index / export seconds |
| --- | --- | ---: | ---: |
| Java | `b624d888e8a35f55c6f43f3255c2b21878d56e75d1e764442e9571d1fa998b23` | 3,886,556 | 8.183 / 3.960 |
| Kotlin | `7a8d957112b48ec2710afb16263211638540d5489b25dc6f313d4dd6b2afbcea` | 3,886,560 | 7.943 / 3.714 |
| JavaScript | `e36126105e72f4a8399254b787bd80c329102e3d872120503721db8f9a943c0e` | 212,640 | 1.008 / 0.269 |

These producer timings are descriptive and excluded from actual model usage; no billing/savings inference follows. Java and Kotlin share a source corpus but have separately produced, internally arm-identical graphs with different recorded revisions.

## Controls and review

All 18 finding citations have positive source-location witnesses and negative quote controls. All 67 source-reviewed semantic clauses (Java24, Kotlin20, JavaScript23) remain mandatory; citation controls deliberately use non-semantic placeholder explanations and do not demonstrate full answer quality.

The reviewed relationship sets contain Java8, Kotlin4 and JavaScript4 actual source-supported calls. Both runtime variants deliver each in JSON and text: 32 +16 +16 =64 positive command captures. Wrong-line and failed-command controls reject. All three multi-range quote controls pass (6/20/16 source rows respectively), never earn relationship credit, and the control runtime rejects archive-quotes without stdout. Corrupted quote controls reject; the focused unit suite additionally isolates canonical-rendered wrong quote content, hashes, coordinates and language to ensure rejection is not merely formatting. Independent collector replay reconstructs argv/events/hashes and recalculates every positive/negative result, not just saved booleans.

Known omitted Java get→put and this.writeOperations.drain calls, the missing Kotlin bridge edges, and missing Express download→this.sendFile edge remain explicit in source reviews. The final relationship inventory was selected from source-verified actual edges before model execution; no task, semantic clause or source bytes were substituted. Constructor calls that target stored class nodes are identified as such, not fabricated method targets.

The runner/collector/recognizer were independently reviewed. All six order permutations are balanced. Before every launch the full frozen inventory, environment and all three arm preflights are checked, and captured controls are replayed. Terminal process status is saved before postflight/parser work; integrity postflight executes even for malformed JSONL. An integrity or parser exception stops that group without retry. Ordinary terminal model failures remain scheduled failures and do not trigger retries. UTF-8 LF prompt bytes written to disk equal the binary stdin bytes sent to the child, including on Windows paths; the actual model cohort is pinned to the recorded macOS environment.

## Tests and limitations

Passed locally: 51 new model-free tests (18 protocol, 16 gate, 17 evidence), 132 complete root tests including those 51, 317 engine tests, and 29 exploration harness tests. Tests cover failure-path preservation, exact file/command/hash/usage/semantic binding, optional quote adoption, strict per-pair input/output reductions, primary/secondary separation, no-overwrite output, extra/missing records, stale source, malformed packets and controls, and path/newline portability. An initial engine discovery invocation picked the main worktree's older editable package and failed two imports; rerunning with this worktree's explicit PYTHONPATH passed all 317, without changing production code or model inputs. This local invocation correction is not a model retry.

Existing PR17 merge commit platform checks also passed: [PR run34256847070](https://github.com/ch4570/columbus/actions/runs/34256847070) and [push run34256840834](https://github.com/ch4570/columbus/actions/runs/34256840834), all12 Linux/macOS/Windows × Python3.11/3.14 jobs. This does not replace final-head CI for the new evaluation PR.

No actual model result is asserted here. The old cohorts' token/quality failures remain unchanged. Freeze input-hashes.json, commit and push the complete prospective protocol before launch; do not edit frozen files after the first model begins. Review and result artifacts will be appended separately. PR12/main/release remains gated.
