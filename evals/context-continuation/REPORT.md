# Bounded receipt continuation: source coverage regression

The frozen previous implementation stops after delivering 20 matching declarations. The candidate reaches all 30 declarations, and all 175 declarations in the larger check, while every serialized response remains within 2,048 UTF-8 bytes. Neither condition repeats delivered source characters. These are model-free retrieval checks, not model-token or billing measurements.

The complete observations are in [working-tree.json](working-tree.json). The run used Python 3.12.14 on macOS arm64; its UTC timestamp, harness hash, complete engine manifests, source manifests, per-call output hashes, counters and byte counts are preserved there.

## Source and provenance

The baseline is pinned to commit `7f4bb077c38eb5b64b8ef06448d36a2f1c399c98`, the previous development merge head. Its frozen package manifest digest is `d169f313f2b141e78880ec7b4dfa577bd68ba99bc3fc86c4f90e26446da1f245`.

The candidate is a frozen working-tree snapshot based on that same commit, **not a committed candidate revision**. Its package manifest digest is `b658b994085ee816ad58509581725455100993b7a2ddc5f7c56741b69f360ddc`. The observation records the six modified runtime files and confirms that their copied bytes did not change during freezing. Later working-tree changes are not part of this observation. A final candidate commit can be checked with the committed replay command below; retain this original record.

Each condition runs in a separate Python process with its own frozen package and temporary repository/index. The fixture contains either 30 or 175 independent Python files, each defining `target()` and returning a distinct `TARGET_NNN` string. The index contains two nodes per file: the declaration and its module. Both conditions receive identical source bytes and repeatedly request `context("target", budget_bytes=2048)` with the same saved receipt, separately for JSON and text.

The harness verifies every returned source hash and character-offset slice against the fixture. It rejects repeated source coordinates and accounts for every non-newline source character; trailing/isolated newlines are excluded from completion because snippet receipts intentionally omit them. Actual newline characters that are returned still participate in the no-overlap check. Source files must remain unchanged. A separate fresh-receipt CLI probe confirms that the first `context --snapshot --receipt ...` response exactly equals the API-rendered response for each condition and format.

## Observed results

Calls include the terminal empty check. The baseline includes a second empty check to establish that its receipt made no progress. Response totals include those checks and exclude the separate CLI validation probe.

| Declarations | Format | Implementation | Complete source files | Context calls | Response bytes total | Largest response |
| ---: | --- | --- | ---: | ---: | ---: | ---: |
| 30 | JSON | Baseline | 20 / 30 | 12 | 21,825 | 2,016 |
| 30 | JSON | Candidate | 30 / 30 | 16 | 31,334 | 2,035 |
| 30 | Text | Baseline | 20 / 30 | 5 | 6,771 | 2,042 |
| 30 | Text | Candidate | 30 / 30 | 6 | 9,865 | 1,888 |
| 175 | JSON | Baseline | 20 / 175 | 12 | 21,825 | 2,016 |
| 175 | JSON | Candidate | 175 / 175 | 90 | 179,919 | 2,033 |
| 175 | Text | Baseline | 20 / 175 | 5 | 6,771 | 2,042 |
| 175 | Text | Candidate | 175 / 175 | 32 | 56,431 | 1,889 |

The baseline's empty responses report `seen_candidates=20`, `omitted_candidates=0`, `stale_candidates=0`, and `truncated=true`; receipt reuse cannot expose the remaining files. Its 740 delivered source bytes cover 720 non-newline characters. The candidate covers all 1,080 required characters for 30 files and all 6,300 for 175 files, delivering 1,110 and 6,475 source bytes respectively. All source-coordinate, hash, immutability, overlap, budget, and CLI-parity checks pass.

For 175 declarations, the candidate produces one empty but advancing continuation response after all source has been delivered, followed by an exhausted response. This reflects the bounded discovery scan over already-received module nodes. The intermediate response reports `has_more=true` and changes the saved cursor; the final response reports `has_more=false` and `truncated=false`. It does not stall on unread source.

The candidate sends more bytes and performs more calls because it completes source coverage that the baseline misses. This is **not an equal-coverage cost-reduction comparison**. Context calls are API invocations, not measured model rounds or shell-command counts. No model ran, and the check does not measure answer quality, semantic graph accuracy, or actual token consumption. Index preparation time is recorded separately and is not included in payload totals.

## Reproduce

From the repository root, use Python 3.11+ with the project's normal dependencies. The harness creates and cleans temporary engine copies, Git roots, indexes, receipts and CLI probes. It does not modify the checkout's runtime or overwrite an existing observation file.

```sh
.venv/bin/python evals/context-continuation/observe.py \
  --output /tmp/context-continuation-new.json

# Include the 175-declaration case beyond the former 150-candidate cutoff.
.venv/bin/python evals/context-continuation/observe.py --large \
  --output /tmp/context-continuation-large-new.json

# Replay a final committed candidate, preserving the old baseline pin.
.venv/bin/python evals/context-continuation/observe.py --large \
  --candidate-ref FINAL_CANDIDATE_COMMIT \
  --output /tmp/context-continuation-committed-new.json
```

Exit status zero means that the expected baseline starvation and complete candidate coverage were both reproduced and all integrity/budget checks passed. An unexpected baseline outcome is reported as a failed regression comparison, not discarded. The default baseline revision is fixed in the harness; `--baseline-ref` is available for an explicitly different comparison, which is recorded with its resolved commit and package hashes.
