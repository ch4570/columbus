# Post-launch development notes

This file is supplemental, not a prospective protocol input. It never replaces
the frozen plan, manifest, criteria, commands or failed historical outcomes.

## Launch and immutable snapshot

The three group runners started on 2026-09-08 at 18:01:11–18:01:14 UTC, after
commit `d4384adc0207a19c59025adc1decc91ab2a20a52` was pushed and PR #18 opened.
All 123 inputs matched their committed Git blobs before launch. The unchanged
input manifest SHA-256 is
`85ac3b856197225df2234c118bde0bacf1382655a45945b5bf03406bbb9c83a8`.

Models run from a separate worktree kept at that original commit. Subsequent
development commits are not retroactively substituted for any launched input.
The original runner, collector and retention preflight must be used with that
exact snapshot: later changes to a manifest-listed test correctly cause the
original frozen-input verifier to reject the newer working tree. Check out the
original commit in a separate worktree instead of rewriting old hashes. Original
absolute observation paths remain part of the captured invocation contract; this
snapshot is not a path-independent model replay command.

## Windows test-fixture newline fix

The original [PR CI run](https://github.com/ch4570/columbus/actions/runs/34260489211)
and [push CI run](https://github.com/ch4570/columbus/actions/runs/34260393100)
each passed Linux and macOS Python 3.11/3.14 but failed both Windows jobs. All
four Windows collector-test failures came from a fixture writing platform-default
CRLF prompt bytes while the collector correctly requires exact UTF-8/LF bytes.
This is not a model outcome or a production-runner failure.

The fixture now writes UTF-8 bytes, matching the already-frozen runner's explicit
LF file write and binary stdin. A regression checks Unicode byte parity and
ensures CRLF tampering is still rejected; the collector is not relaxed. The fix
was prepared in another worktree while the launched snapshot stayed untouched.
The 17 targeted tests passed normally and with simulated Windows default
newlines. All 133 root tests passed locally. Actual final-head Windows CI remains
required; local simulation is not a substitute.

This test-only change does not change a runtime export, prompt, semantic clause,
citation rule, recognizer, model setting, trial order or result. No model retry
or extra repetition is authorized. PR #12 to main and any release remain gated
on the separately stated actual-input-and-output, complete-quality requirements.

PR #19 subsequently passed all 12 exact-head platform jobs at
`e13dd40d120344d730bc366d33afa34861ea7cc6` and merged into the evaluation branch
as `f955dd1d1ed92a28f1f765cda3dfccc19f592161` at 18:20:38 UTC. Both trees are
`44acce7d2cd78380e38a0a7bbe9d269e7eeb2f4c`. The original live worktree remained
at `d4384ad`; no launched input was updated. These are development merges only.

## Supplemental post-run retention utility

`retain.py` and its tests are new, non-frozen supplemental files. The utility
cannot launch, retry or poll a model. Capture requires explicit owner
confirmation that all original runner handles have terminated. Ordinary capture
requires all 18 process/terminal/result records and all three group completion
records, but does not require passing model outcomes. Explicit
`--allow-incomplete REASON` preserves missing, malformed and unexpected trial
evidence after a confirmed stopped partial cohort; absence of a file is never
treated as proof of termination or zero usage.

Capture runs beside the original 123-file snapshot and verifies its exact hash
inventory, plus original observation integrity, before and after output writes.
This later development tree contains the test-only newline fix and is therefore
not a substitute for the original snapshot. A failing source/runtime preflight
refuses capture rather than blessing changed source as the launched input.
Use a new output directory outside the original observations. The tool never
overwrites a destination; a publication failure leaves partial files and an
`INCOMPLETE.json` marker. It has not been run against active model trials.

Expected raw event logs are compressed losslessly with deterministic gzip;
unexpected artifact paths are retained in a disjoint raw namespace so an extra
`events.jsonl.gz` cannot collide with the compressed original. Every retained
file binds original and stored bytes. Source ZIPs, archives, runtime exports,
protocol and rubrics remain at the original commit's 123 hash-linked paths.
Only explicitly selected semantic reviews and a collector report are included;
missing reviews are listed, never synthesized. Original absolute paths are
preserved, not silently remapped into a portable model-replay promise.

`--verify DIRECTORY` checks retained files, decompressed event bytes, all 18
slot-presence summaries and declared process/result fields without the original
observations, installed engine dependencies or model access. The retention
manifest digest must be externally anchored for authenticity. Successful byte
retention is not semantic approval or cost acceptance.

Fourteen synthetic, model-free tests pass. Independent review found and then
rechecked malformed runner-record handling, compressed-name collisions and raw
record/summary consistency. No original experiment input or grader was changed
to address these supplemental-tool defects.
