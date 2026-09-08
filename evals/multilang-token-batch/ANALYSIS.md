# Multilingual token measurements and diagnosis

The fixed cohort completed all twelve executions (six pairs). None reduces both actual total input and output; both increase in every pair. This fails the mandatory release threshold regardless of quality scoring. No model is retried or additional cohort started.

| Task / repetition | Baseline input | Columbus input | Input change | Baseline output | Columbus output | Output change |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| java / 1 | 166,153 | 653,513 | +293.32% | 8,928 | 14,872 | +66.58% |
| java / 2 | 323,091 | 418,839 | +29.63% | 8,708 | 13,107 | +50.52% |
| kotlin / 1 | 115,847 | 399,328 | +244.70% | 6,807 | 10,172 | +49.43% |
| kotlin / 2 | 158,702 | 267,222 | +68.38% | 5,691 | 10,426 | +83.20% |
| javascript / 1 | 56,133 | 306,870 | +446.68% | 11,202 | 14,574 | +30.10% |
| javascript / 2 | 170,888 | 221,510 | +29.62% | 12,368 | 13,455 | +8.79% |

Input includes its cached subset; cached, uncached and reasoning subsets remain in each raw result. Counts are runtime-reported usage from the requested `gpt-5.6-sol` / `xhigh` settings, not estimates, prices or backend-model attestations. There is no averaging of failures into acceptance.

All six Columbus executions used successful graph evidence and the new batch-source operation. Offering the feature was therefore not the only observed mechanism. Its use did not produce a passing token result in this cohort.

The first Java Columbus answer used 36 shell commands versus 13 for baseline, including repeated declaration searches before batch reads. Both Kotlin Columbus executions combine graph retrieval with ordinary source reads; the second returns fewer command-output bytes while still increasing actual input/output. Both Express Columbus executions use 22 commands, including discovery and source reading after graph excerpts. These trace observations identify remaining exploration overhead; they do not causally allocate model tokens to individual commands or isolate the batch feature from the skill/runtime package.

The automated [cohort gate](REPORT.md) and [raw result data](results.json) also retain every citation failure and the independently reviewed semantic omissions. Reviews apply all predeclared clauses without relaxing the rubric; omission of required details is distinct from an incorrect executable graph edge. No project build or external engine behavior was used as an answer oracle.

The cohort spans three tasks in two repositories: Java and Kotlin/Java use the same Spring source, while JavaScript uses Express. It is not six independent repository samples or evidence about all supported languages. The [eleven earlier failed pairs](../model-usage-overview/REPORT.md) remain unchanged.

## Evidence and replay

The model runtime and 34 protocol inputs are frozen at `e0694bf7b223d9e034565f964e1747f84e056505`. A separate worktree corrected Windows synthetic command-path spelling in a test at `86431a0d99dfce1b58b178b403ddd41015f543b7`; it changes no model runtime, skill, harness or rubric. Final collection was performed before fast-forwarding the original worktree, and the original input hashes remain unchanged.

Each language directory contains `trials/` with prompt, invocation, answer, result and losslessly compressed raw `events.jsonl.gz`; decompressed event hashes equal each recorded `events_sha256`. [Artifact hashes](raw-artifact-hashes.json), [terminal process receipts](terminal.json), [review provenance](review-provenance.json) and clause reviews retain all runs, including failures. Full local source/runtime/archive snapshots are retained under the ignored `.omx/observations/multilang-token-batch/{language}/observation` directory. The frozen preparation files retain their original pre-execution status descriptions.

The collector never runs models. Recompute it in a worktree at the frozen commit, copy the final language `semantic/` directories there, and restore the recorded observation directories at `/tmp/columbus-token-{language}-batch` with matching source/runtime/archive hashes; then run `python evals/multilang-token-batch/collect.py`. Its exit code 1 is the expected failed acceptance result. Running it on the later Windows test-fixture revision intentionally rejects that changed frozen input; do not rewrite the old hash inventory to make it pass.

The local 263-test engine suites, 58 root tests, 21/21 multilingual contracts and clean wheel/ZIP installation pass. The Windows correction passes the [six-platform PR workflow](https://github.com/ch4570/columbus/actions/runs/34214220580) and [push workflow](https://github.com/ch4570/columbus/actions/runs/34214218220). Final reporting-commit checks are linked from PR #12. These functional results do not satisfy the failed token gate. No merge, tag or release was performed.

## Complete quality scoring

Both citation checks and every semantic clause are required for each answer. The table keeps their distinct pass counts; neither partial quality nor lower response bytes waives a failure.

| Task / repetition | Baseline citation | Columbus citation | Baseline semantic clauses | Columbus semantic clauses |
| --- | ---: | ---: | ---: | ---: |
| java / 1 | 5/5 | 5/5 | 19/22 | 19/22 |
| java / 2 | 1/5 | 4/5 | 20/22 | 18/22 |
| kotlin / 1 | 0/5 | 5/5 | 17/19 | 18/19 |
| kotlin / 2 | 1/5 | 5/5 | 19/19 | 19/19 |
| javascript / 1 | 4/6 | 5/6 | 22/26 | 19/26 |
| javascript / 2 | 4/6 | 5/6 | 21/26 | 18/26 |
