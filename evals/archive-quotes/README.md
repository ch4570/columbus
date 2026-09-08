# Exact-range quote extraction: model-free workflow

This checks a new Requests session-lifecycle extraction operation on a previously used public repository. It is not a held-out repository, an answer/semantic evaluation, a rerun of a historical cohort, or an actual-model token gate. No historical answer or rubric supplies the pass criteria. Expected source comes directly from the independently hash-checked pinned files.

The four requests are `src/requests/api.py:55–59` and `src/requests/sessions.py:451–452`, `454–455`, `794–797`: the top-level request's session context, context-manager entry/exit and adapter cleanup. The test checks extraction correspondence, not runtime behavior or whether these snippets alone support an arbitrary explanation. All variants must return the same 13 ordered `(path, line, text)` rows and 548 decoded quote bytes.

## Inputs and initial capture

Requests [commit b25c87d7cb8d6a18a37fa12442b5f883f9e41741](https://github.com/psf/requests/tree/b25c87d7cb8d6a18a37fa12442b5f883f9e41741) is the recorded v2.32.5 source pin. The pre-existing ZIP is `753ea160ac0af1c4c83c584c6f05bebe716ca5d3b0780802bc8cbc8d5d82adab`; it contains 132 files / 5,190,867 uncompressed bytes under `requests/`. Initial capture requires the complete matching extracted snapshot, excluding only `.git` metadata. It neither downloads nor regenerates source or graphs.

The original graph must remain byte-identical: SHA-256 `f315a1101ab14109424a60ce8c3b459f422808962fe74db5065462afacd6d3de`, 173,816 bytes. The complete artifact is validated by each archive command; no graph is regenerated from the smaller retained fixture.

From this checkout, with the compatible development interpreter:

```sh
/Users/rex/Desktop/personal/columbus/.venv/bin/python -B evals/archive-quotes/verify.py \
  --repo /tmp/columbus-requests-redirects-v3-trial/repository \
  --archive /tmp/columbus-requests-redirects-v3-trial/graph.jsonl.xz \
  --source-zip /tmp/columbus-requests-redirect-source.zip \
  --output-dir evals/archive-quotes/retained
```

The output directory must not exist. The script executes exactly three read-only variants: one `archive-quotes` batch, one existing `archive-source` batch, and one compound ordinary `sed` read. It checks source/runtime/archive hashes before and after execution. Target Python code is never imported or executed; there are no models or network calls.

The existing batch is an efficient equal-source comparator, not four separate calls: ordered exact IDs for `request`, `Session.__enter__`, `Session.__exit__` and `Session.close`, with `--offset 41 --limit 13`, skip only the request declaration's preceding documentation. Both archive variants use a 6,000-byte budget. The ordinary comparator uses one non-login `/bin/sh -c` invocation containing two `sed` commands, with multiple exact ranges in the second command; login profiles are not loaded.

## Measurement and metadata boundaries

The initial read-only observation returned **1,563 bytes** for quotes, **2,104 bytes** for the existing text batch and **552 bytes** for ordinary reads, each including its final newline. Quotes were 541 bytes smaller than that batch and 1,011 bytes larger than ordinary source output. Retained `results.json` and exact stdout/stderr files are authoritative for this capture; all return codes must be zero and stderr empty.

Source coverage is equal, but metadata is not. Quotes retain explicit requested paths/ranges, full-file hashes, language, revision, freshness and an untrusted-source warning. The existing batch also retains declaration IDs/full declaration bounds/fidelity/partial flags and union-pagination metadata (`total_lines=54`, `offset=41`, `truncated=true`, `next_offset=null`). Ordinary reads contain source alone: the comparison script reconstructs their coordinates from the predeclared requests, not from output provenance.

Command UTF-8 bytes are measured separately using `shlex.join(argv)`. They depend on concrete interpreter/checkout/input paths and shell quoting, and are not model input tokens. Neither fewer bytes nor copy-ready JSON establishes semantic correctness, fewer transcription mistakes, end-to-end navigation efficiency, or lower actual input/output token usage. The utility remains optional: source already in context need not be read again.

During development, a first capture passed its before/after runtime checks; a subsequent no-write replay correctly refused to execute after separate CLI/error-handling fixes changed two runtime hashes. That pre-hardening capture was preserved outside this checkout at `/tmp/columbus-quote-validation.w8jBVL/pre-hardening-replay`, not overwritten or relabeled. Its `results.json` SHA-256 is `c60371de15e5c63d353936859f7b4a9b802285d8b5a59cd77dbf45b6aae90c76`. Final retention uses a fresh destination after the runtime stabilizes, with the same four ranges and comparators; this is model-free functional validation, not a selective historical/model-cohort rerun. Canonical `/private/tmp` paths made the first capture's command counts 469/535/127 bytes, versus 445/511/127 in the earlier `/tmp`-spelled observation; the three stdout hashes and byte counts were unchanged.

The final comparator replaces `/bin/zsh -lc` with `/bin/sh -c` to avoid login-profile effects and an unnecessary zsh requirement. Its command is 125 bytes with the same source output; this does not relabel the earlier 127-byte zsh observation. Final capture command counts are 469/535/125 bytes; replay's archive-command lengths can change with the retained fixture's path.

Final capture and the subsequent no-write minimal-fixture replay both passed, with identical stdout hashes for all three variants and unchanged source/runtime checks. The final [results manifest](retained/results.json) SHA-256 is `b183e969904c04c150f7a1626565c2e26f539336656ebc854ca1225b9f7fecca`. The existing-destination guard also rejected a capture attempt before any variant ran and preserved the retained bytes.

## Retention and offline replay

`retained/` contains the exact original graph, raw outputs, a hash/argv/results manifest, and a **minimal fixture of two full selected source files plus the original Apache-2.0 LICENSE**. It is not the 132-file repository. The full ZIP is intentionally external; its path/hash and the complete initial 132-file validation inventory are recorded. The source license is not a license statement for the surrounding Columbus code.

```sh
/Users/rex/Desktop/personal/columbus/.venv/bin/python -B evals/archive-quotes/verify.py \
  --replay-from evals/archive-quotes/retained
```

Replay verifies all retained payload hashes, the original graph and selected-source pins, and every recorded Columbus Python module, CLI shim and this verifier. It then executes exactly the same three variants against the minimal fixture and requires byte-identical stdout. It does not need the ZIP and explicitly does **not** revalidate the full original repository. Runtime files are not copied: replay requires their recorded bytes in this checkout, a compatible Python and `/bin/sh` with `sed`. No portability claim is made for interpreter binaries, standard-library builds or installed dependencies. Skills/references are not read by these model-free commands and are not part of the runtime fingerprint.

Without `--output-dir`, replay prints a verified report and writes nothing. A fresh `--output-dir` optionally retains a new replay result. Existing destinations are refused; an I/O failure can leave a partial destination and is not permission to overwrite it. Inputs and runtime hashes are checked before capture publication; generated artifacts never alter historical cohorts.
