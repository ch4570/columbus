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
