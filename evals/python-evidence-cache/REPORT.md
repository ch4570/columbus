# Reuse physical line indexes for Python evidence

Python reference extraction called ast.get_source_segment for each reference, repeatedly splitting the entire file. The adapter now caches UTF-8 physical lines once and slices with AST byte offsets. Normalization and the existing evidence cap remain unchanged. CR, LF, CRLF, Unicode identifiers, emoji and non-newline Unicode separators are compared directly with the standard-library result; AST nodes lacking source coordinates retain unparse fallback.

Seven Django production files containing iri_to_uri calls were parsed by the prior and current adapters. Every complete parsed record is exactly equal; raw source/fact hashes are retained. Single-run totals are 1.6259 seconds before and 0.02847 after. Baseline ran first with unflushed OS caches on a shared host. This is a file-parse comparison, not end-to-end index latency or model-token savings.

Both parser environments pass 214 engine tests; root tests pass 53. The independent Django caller oracle does not use this adapter. A separate full Django index attempt using the old adapter terminated on a PNG fixture named file_png.txt, so no full-index speed comparison or caller-graph parity is claimed yet. That failure remains open and blocks the proposed model trial. See ../django-callers/binary-failure.json.
