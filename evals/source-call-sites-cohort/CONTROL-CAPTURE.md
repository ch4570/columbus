# Original model-free capture and prospective dispatch optimization

The 303 prescribed commands are assigned to three independent, one-shot capture
processes started with the code later committed unchanged in
`129da366bf1dcaf2b848d43cc8b2637064938b74`. The original processes retain their
already imported modules; they are not stopped, restarted or reloaded for the
subsequent adapter optimization. They finish their original capture and replay.
No model has been launched and no input-hash freeze existed when the optimization
was made. The exact original outputs, errors, attempts and recognition results
remain primary evidence, not replacements synthesized by the newer adapter.

| Language | Attempt start (UTC) | Prescribed commands | Original attempt SHA256 |
| --- | --- | ---: | --- |
| Java | 2026-09-08 20:39:27.075881 | 117 | `8d84db9e9f04e084dde6e98c5f17dc1b32239714d92b4eb5596941a3261be4f9` |
| Kotlin | 2026-09-08 20:39:27.066255 | 51 | `6d7200a7c660123de6f932677acb1c8ff6a168018f147a5d21defb868a9ab3b3` |
| JavaScript | 2026-09-08 20:39:23.403389 | 135 | `3301ce71bdc0134ea3eac45af342d12646487939e3ff6670df1f43fa63b6008e` |

The attempt markers contain actual specifications, process identity and start
times. They did not contain a per-process code-hash attestation. The following
table records the integrating agent's launch provenance and exact Git bytes,
not an invented external or per-process cryptographic attestation.

| Original capture dependency | SHA256 at the committed capture version |
| --- | --- |
| `evals/source-call-sites-cohort/controls.py` | `ad0c5cbe364ad70d0acc9d16e64caed0adbc63e133c65234e23c2be673328683` |
| `evals/source-call-sites-cohort/recognize.py` | `6982c60da49047f5d4d94d4c1f706ec0e80f0ee46fbacd3e1de116bdcaeec54f` |
| `evals/source-call-sites-cohort/common.py` | `e035922cb0714df71a32678cb5ceaf982dcbc252ee9d5fd9fc08a9049b541dad` |
| `evals/exploration/source_call_evidence.py` | `5f7fdf492ab5ea6e9f23b2be2f74b6be4978209ee267180fde9c8d904c193150` |
| `evals/quotes-three-arm/recognize.py` | `1116e46f1fad5323de7d738c8c3498149ab3b99fae73e3705609c4690e7bca8f` |
| `evals/exploration/archive_evidence.py` | `e886ddb102e7b2b3f6cdfc09f0e32b1d6d321f3bd1af6ac791844b9e8bfbd963` |
| `evals/archive-exploration/preflight.py` | `981d18f13648886ac4198caba36339f8d855d4f02bbea1f75ae26d0268326869` |

## Why dispatch changes before freeze

Offline profiling of the already completed Java `control-raw/000.json` showed
the original adapter constructing a complete source/call snapshot even though
the command was `archive-neighbors`. Under cProfile, one recognition took
3.85465 seconds; 3.827 seconds were in the irrelevant source/call branch, which
read 150517 graph records and returned no source/call receipt. Its useful legacy
relationship receipt was separate.

The prospective adapter first applies necessary command/event conditions using
the same quoting-aware tokenizer and permitted single-shell unwrap. It requires
a successful completed command with the exact Python/wrapper prefix and exact
`archive-source` / `--call-sites` tokens. It does not filter on output validity.
If any candidate exists, the complete original event stream still passes through
the unchanged standalone recognizer and its full snapshot checks. False-positive
screens are safe because the full parser remains authoritative. Independent
review found zero false negatives across 532 full-parser-accepted spellings.

When no candidate exists, only the empty source/call contribution is omitted;
legacy receipt processing is unchanged. This adapter depends on the cohort's
authoritative full common pre/postflight and frozen-input checks. It does not
offer the standalone recognizer's empty-stream configuration validation contract.
The standalone source/call module remains byte-identical to the capture version
and still verifies all frozen inputs for empty or failed-only streams.

The same original Java packet took 0.02087 seconds under cProfile through the new
adapter, with identical receipt values and unchanged raw bytes. This is offline
recognizer CPU evidence, not model-token, bill, end-to-end cohort-time or runtime
feature savings. Unit tests also relocate the complete pinned Java source,
runtime and graph into fresh temporary inputs and rebase only invocation paths;
original full recognition and optimized recognition produce byte-identical
receipts. That test is offline saved-packet replay, not another captured command.

Every original completed control must still reproduce under the optimized
adapter before freeze and before each future model execution. The 303 prescribed
commands, task clauses, reviewed edges, strict actual input AND output criteria,
historical failures and no-retry policy are unchanged. Final capture/replay
completion is recorded separately in `PREFLIGHT.md`; this document alone does
not assert that currently running captures have finished.
