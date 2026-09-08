# Completed quotes three-arm experiment

**Rejected.** None of the six primary baseline-versus-quotes pairs has both strictly lower actual total input and total output. All six fail the complete pair gate; all six secondary control-versus-quotes pairs also fail. No main merge or release is supported. Earlier failed experiments remain failed.

This is a post-run report, not a new protocol or regrade. The [machine report](retained/collector-report.json) verifies all 18 scheduled executions, all three fixed orders and all 123 frozen inputs with no collection errors or pending reviews. Every process exited 0 without a timeout; one execution-policy review fails independently of process exit. The original runner handles were confirmed terminated before capture. No retries, added repetitions, repaired answers, changed prompts or relaxed criteria were used.

## Actual usage and full quality

B = ordinary-tool baseline, C = Columbus control `9c0d3c3a54022237d32b9790ba4c1e0b2a758124`, Q = quotes runtime `402940994ba519a3a02a521ccfed55b73d310dbf`. Each language has two repetitions. Requested model/effort was `gpt-5.6-sol`/`xhigh`; this is recorded invocation configuration, not independent backend attestation. These are reused repositories with new operations, not held-out-repository evidence. Source scope and provenance remain those in the frozen per-language source reviews.

Counts below are reported runtime tokens, not estimates from source, tool output or final-answer bytes. Cached input is a subset of total input; reasoning output is a subset of total output. Cache-write input is zero. Full usage fields, command receipts and hashes are in the machine report and raw records.

| Run | Total input | Cached input subset | Total output | Commands | Exact citations | Semantic clauses | Execution | Reviewed graph receipt |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- |
| Java B1 | 112,670 | 76,800 | 19,251 | 6 | Fail | 20/24 | Pass | N/A |
| Java C1 | 194,183 | 142,976 | 15,807 | 13 | Pass | 20/24 | Pass | No |
| Java Q1 | 372,639 | 303,232 | 15,831 | 25 | Pass | 20/24 | Pass | No |
| Java B2 | 104,721 | 69,376 | 14,415 | 5 | Fail | 21/24 | Pass | N/A |
| Java C2 | 221,295 | 165,376 | 14,116 | 10 | Pass | 23/24 | Pass | No |
| Java Q2 | 294,312 | 232,960 | 15,382 | 18 | Pass | 19/24 | Pass | No |
| Kotlin B1 | 106,812 | 62,464 | 9,075 | 13 | Pass | 17/20 | Pass | N/A |
| Kotlin C1 | 190,362 | 146,944 | 9,476 | 8 | Pass | 16/20 | Pass | No |
| Kotlin Q1 | 734,845 | 670,976 | 16,830 | 19 | Fail | 17/20; wrong finding IDs | Fail | No |
| Kotlin B2 | 90,996 | 36,480 | 8,785 | 12 | Pass | 16/20 | Pass | N/A |
| Kotlin C2 | 150,501 | 115,072 | 9,327 | 6 | Fail | 17/20 | Pass | No |
| Kotlin Q2 | 311,959 | 268,928 | 13,541 | 23 | Pass | 18/20 | Pass | No |
| JavaScript B1 | 66,092 | 31,360 | 7,072 | 5 | Pass | 23/23 | Pass | N/A |
| JavaScript C1 | 152,864 | 115,968 | 13,832 | 10 | Fail | 23/23 | Pass | Yes |
| JavaScript Q1 | 89,677 | 61,184 | 11,071 | 10 | Pass | 23/23 | Pass | Yes |
| JavaScript B2 | 40,488 | 23,296 | 9,375 | 4 | Pass | 23/23 | Pass | N/A |
| JavaScript C2 | 106,934 | 86,016 | 13,214 | 7 | Fail | 23/23 | Pass | Yes |
| JavaScript Q2 | 115,356 | 77,184 | 12,185 | 9 | Pass | 23/23 | Pass | Yes |

All 18 independent semantic reviews bind exact answer, frozen rubric and event hashes and assess every clause using only support in that answer. Substantive clause counts do not waive required finding identities or full semantic acceptance. Only the six JavaScript answers pass all semantic requirements. Kotlin Q1 uses eight different IDs rather than the six required IDs, so all six required finding-level verdicts fail despite 17 supported substantive clauses. Its five Columbus invocations also use `python3` instead of the explicitly required absolute interpreter plus `-B`; this is an execution-policy failure, not a timeout or fabricated usage.

Citation failures remain literal failures: four Java B1 excerpts include an extra closing-brace line; Java B2 removal declares 229–253 but includes 254; Kotlin C2 storage declares 43–46 but includes 47; JavaScript C1/C2 finish-race quotes each extend one line past the declared end. Kotlin Q1 has no required finding IDs. The other twelve runs pass all required citation checks. No quoted range was widened after the fact.

No Java/Kotlin graph arm receives a recognized, pre-reviewed relationship receipt. Source, declaration search, exact quotes or a zero-edge response are not substituted for graph utility. All four JavaScript graph arms receive the stored `sendFile` → `sendfile` edge at `lib/response.js:406`; that is saved evidence, not complete runtime dispatch. All six Q runs receive recognized exact-quote packets, which are optional source delivery and not graph evidence or proof of semantic support. The [JavaScript diagnosis](DIAGNOSIS.javascript.md) distinguishes quote adoption, useful edge delivery and token accounting in detail.

## Per-pair decisions

Deltas are Q minus the comparator. Strict cost success requires both values below zero on the same pair, plus all frozen quality/utility conditions. No averaging, cached-subset substitution or favorable secondary comparison changes a primary failure.

| Language / repetition | Primary input delta (Q−B) | Primary output delta | Secondary input delta (Q−C) | Secondary output delta |
| --- | ---: | ---: | ---: | ---: |
| Java 1 | +259,969 | −3,420 | +178,456 | +24 |
| Java 2 | +189,591 | +967 | +73,017 | +1,266 |
| Kotlin 1 | +628,033 | +7,755 | +544,483 | +7,354 |
| Kotlin 2 | +220,963 | +4,756 | +161,458 | +4,214 |
| JavaScript 1 | +23,585 | +3,999 | −63,187 | −2,761 |
| JavaScript 2 | +74,868 | +2,810 | +8,422 | −1,029 |

JavaScript secondary repetition 1 alone has both lower token totals, but its control citation fails, so its pair still fails. All primary pairs fail before any quality waiver could matter. The machine report preserves every additional semantic, citation, execution and graph-utility failure reason separately.

## Evidence retention and verification

The frozen launch commit remains `d4384adc0207a19c59025adc1decc91ab2a20a52`. The original three groups started at 18:01:11–18:01:14 UTC on 2026-09-08; the last model process finished at 18:55:57 UTC. Kotlin and JavaScript original runner handles closed first; the final Java handle was polled and confirmed exit 0 before capture. The post-run capture is timestamped 19:07:13 UTC.

[RETENTION.json](retained/RETENTION.json) binds 198 payload files, including all 18 raw event logs (lossless deterministic gzip), prompts, invocations, process/terminal records, stderr, answers, results and semantic reviews, all three group terminal records, arm manifests and this exact collector report. The capture has no issues or missing reviews. Its 123 frozen source ZIP/graph/runtime/protocol inputs remain hash-linked to the original Git paths rather than duplicated. Original absolute paths are preserved; this is not a path-independent model replay bundle.

- Retention manifest SHA-256: `d324e0fea704fd00d17fe182adac0c45d5bdaf492ebbafcd6800704604bc9a04`.
- Collector report SHA-256: `723f580991cb7e4f6419b6b607ea62c2aebe899e347e93f466c350e43f266bda`.
- Frozen input manifest SHA-256: `85ac3b856197225df2234c118bde0bacf1382655a45945b5bf03406bbb9c83a8`.

Read-only standalone byte verification, without the original observations, model access or engine dependencies:

```sh
python -B evals/quotes-three-arm/retain.py --verify evals/quotes-three-arm/retained
```

The manifest digest needs an external trusted anchor; a self-consistent rewritten manifest is not authenticity proof. Re-running the original collector requires the original frozen worktree and observation paths. The later Windows test-fixture correction must not be substituted into that frozen input inventory. See [post-launch chronology](POSTLAUNCH.md).

Subsequent implementation, including an optional source-plus-call-site packet, is a new intervention requiring a separate prospective evaluation. These runs neither test it nor authorize replacing historical failures. Development PRs may preserve the evidence and improve implementation; PR #12 to main and a release remain blocked by the stated acceptance conditions.
