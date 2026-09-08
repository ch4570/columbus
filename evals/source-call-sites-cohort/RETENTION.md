# Post-run lossless evidence retention

This utility is a post-observation packaging step, not a new frozen model input,
grader, collector, benchmark retry or portable replay environment. It never
starts a model, polls a PID, changes a review or recomputes quality acceptance.
It is developed separately while the already frozen model schedule runs.

The frozen experiment remains pinned to commit
`28bfa454044f88e2cc0096f509ae316a4676f209`, tree
`f928f15d855852b25acd996b899b159e958abf46`, and its 449-file input inventory:
SHA256 `69f196d7db2fac0248805878f294966774346028dee725f439707702d60c2fa6`.
All referenced local bytes and their exact pinned Git blobs must agree before
the tool imports the frozen private harness. The original frozen checkout must
remain available and unchanged; do not advance it to the packaging branch.

Only after checking every original runner handle has terminated, first select
the complete independently reviewed collector report, then capture into a new
directory outside the frozen checkout and original observations:

```sh
python -B evals/source-call-sites-cohort/retain.py \
  --frozen-repo /tmp/columbus-call-sites-cohort.Q0BUvh \
  --terminal-confirmed \
  --semantic-dir /tmp/columbus-call-sites-cohort.Q0BUvh/evals/source-call-sites-cohort \
  --report /absolute/path/to/selected/results.json \
  --output /absolute/path/to/new-retained-directory
python -B evals/source-call-sites-cohort/retain.py \
  --verify /absolute/path/to/new-retained-directory
```

The tool requires all 18 scheduled terminal/result records and three completed,
correctly ordered runner groups by default. A genuinely partial/failed collection
can instead be preserved with an explicit `--allow-incomplete REASON`. That
option records issues and missing slots; it cannot produce a cost/quality pass.
Do not infer process termination from missing metadata or use this option while
an original process is still live.

All original trial files, unsuccessful commands, stderr, invocation/prompt,
process/terminal/result receipts and selected reviews/report are retained.
Unexpected files use a separate namespace so an extra gzip-named artifact
cannot replace an original event stream. Event JSONL is losslessly gzipped with
both original-byte and compressed hashes. Missing answers use the collector's
empty-string hash convention; a present empty answer retains the real SHA256
of its zero bytes. Recorded parsing failures are never repaired into metrics.

Source/runtime/archive, source file bytes and complete directory inventories are
checked before and after output writes. Existing outputs are never overwritten;
failed publication keeps its partial files and an incomplete marker when possible.
The standalone verifier checks retained files, decompressed bytes, metadata,
runner ordering and review/report bindings without original observations or an
installed model runtime. Full source/runtime/protocol inputs remain commit-linked
rather than duplicated. Original absolute paths are preserved, so this is not a
portable model or collector replayer. An externally recorded manifest hash is
needed for authenticity; internal hash consistency alone is not authentication.

The synthetic tests use tiny temporary fixtures and forbid external processes.
Their name, `test_postrun_source_retention.py`, deliberately stays outside the
already frozen `test_source_call*.py` input-discovery pattern. Packaging files
and tests must not be introduced as new dependencies of the running experiment.
No actual collection or retention was performed while preparing this utility.
