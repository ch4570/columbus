# Continuous-context preflight on real source

The existing receipt mechanism was exercised on the current `receipts.py` implementation with three sequential queries: `ReceiptFile`, `ReceiptFile.save`, then `ReceiptFile` again. This is a transport preflight for a new continuous-work evaluation, separate from the compact-caller pilots.

| Query | Without receipt: response / source bytes | Retained receipt: response / source bytes |
| --- | ---: | ---: |
| Class | 8,078 / 5,514 | 8,151 / 5,514 |
| Overlapping method | 8,663 / 5,512 | 847 / 0 |
| Class revisit | 8,078 / 5,514 | 842 / 0 |

Total responses decreased **24,819 → 9,840 bytes (60.35%)**. Every returned source slice was checked against original decoded-source offsets and raw hashes. No previously delivered character was repeated with the retained receipt. A new receipt re-emitted source, and changed file bytes followed by real resynchronization invalidated the old ranges and re-emitted them with the new hash. The original repository file was never modified; checks use a temporary copy.

[verify.py](verify.py) reproduces the sequence and negative lifecycle checks; [results.json](results.json) records source/analyzer hashes and per-query measurements. Run `.venv/bin/python evals/continuous-context/verify.py /tmp/continuous-results.json` from the repository root.

This compares graph retrieval with/without receipts, not a model using graph versus a model using ordinary search. It proves neither actual token savings nor answer quality. The old single-turn model pilots used ephemeral sessions and cannot serve as retained-memory continuation trials.

The next actual-model evaluation must create fresh persistent sessions for both arms and resume their exact recorded thread IDs. Do not use `--last` or seed a new model with receipts for source it has never seen. Deliver successive questions after earlier turns complete, retain raw per-turn events, establish whether reported usage is per-turn or cumulative before aggregation, and verify task answers against source. Only receipt/log writes should be permitted in the Columbus arm; source and index mutations remain forbidden. Both arms must retain their own previous conversation, and source hashes must be checked throughout. Predeclare the sequence and all quality gates before model execution.

## Continued-event validation

`audit_events.py CAPTURE.jsonl ... --output REPORT.json` now validates recorded thread UUID continuity, exactly one successful terminal turn per capture, event order, duplicate capture hashes, nonnegative integer usage and the cached-input subset. It preserves raw counters without summing them. A single real historical event file was successfully audited; two unit tests cover a valid two-turn sequence plus six rejected mutations (thread change, missing completion, data after completion, impossible cache count, boolean counter, and duplicate capture).

The synthetic continuation test does not demonstrate a real resumed model session. Source retention after compaction, answer quality, source immutability and provider usage semantics remain separate required gates. This validator is an audit component, not yet an end-to-end continuous-model runner.

A subsequent [live two-turn preflight](resume-preflight/README.md) confirmed exact-ID continuation and exposed cumulative CLI completion counters in version 0.153.4. The audit tool now supports explicitly verified cumulative mode with adjacent deltas, while leaving default aggregation unproven. The earlier synthetic tests are no longer the only evidence for continuation, but a real source-work comparison remains pending.
