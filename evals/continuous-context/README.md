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
