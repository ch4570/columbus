# Preserve physical source lines in graph evidence

A Python string containing U+2028 exposed a real citation defect at 5b24630. `callers` reported call_line=4 and the correct raw file hash, but returned a split string fragment instead of the call. General `str.splitlines()` treated Unicode separators and control characters inside source literals as physical newlines. The same transformation affected FTS bodies, symbol/context excerpts, truncation and text line numbering.

Source extraction now splits physical newline sequences, preserving characters inside literals. Python supports LF/CRLF/CR; Java/Kotlin use the parser's LF coordinates with CRLF normalization. Already-normalized excerpts split on LF only. Text output escapes NEL/U+2028/U+2029 visibly instead of introducing extra display lines. JSON retains the original characters.

[Before/after reproduction](results.json) uses an isolated copy of the old engine and the same SQLite/source with the updated engine. Raw source bytes/hash stay unchanged; the corrected excerpt includes the actual fourth-line call. The decoded-view hash changes, so old receipt ranges fail the existing two-hash compatibility check. Run `.venv/bin/python evals/source-lines/verify.py OUTPUT.json` to reproduce against the recorded old commit.

Validation: 15 Python separator/newline combinations and four Java/Kotlin newline combinations preserve exact call-line content. Both pinned and candidate parser environments pass 198 engine tests; root tests pass 53. The [clean wheel/standalone/relocated-ZIP probe](distribution.json) passes with a Unicode-separator caller fixture added to the installation verifier. Existing budget, stale-source, context and receipt regression tests remain passing.

The earlier numbered-caller CI at 5b24630 passed 19 jobs but did not contain this boundary fixture. Those green checks did not prove source fidelity for this case. Hosted validation of this correction is pending. Broader graph precision, release selection and actual model-token savings remain open.
