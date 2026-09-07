# Archive relationship text output

Add optional `archive-neighbors --format text` to avoid repeating endpoint IDs and file hashes for each edge. JSON remains the default. Text consists of metadata and labelled JSON rows: files, numbered declarations, and relationships referring to page-local node/file numbers. Every relationship field, original serialized evidence, source hash, partial flag and uncertainty value remains available. Control characters are escaped.

The renderer participates in the byte-budget loop, including its final newline. Therefore its page boundaries can differ from JSON: use the returned next_offset and keep the same format and frozen archive. No archive format, SQLite schema or parser behavior changes.

On the retained Django capfirst archive, the exact same 23 incoming edges require 17,259 output bytes as JSON and 12,870 as text, a 25.43% reduction. Both still require three pages at a 6,000-byte budget. The first prototype retained repeated edge paths and used 13,679 bytes; initial-measurement.json preserves that intermediate diagnostic. The final representation also refers to file numbers in edges.

This is a deterministic output comparison, not a model token experiment. The fixed-order timings (JSON 9.038 seconds, text 9.795 seconds) are individual warm-cache diagnostics and do not establish a latency advantage. The previous model timeout remains unchanged; no completed trial was replayed and no savings claim is made.

Validation reconstructs complete nodes and edges from text rows and compares them exactly with packets across pagination, including 24 calls with distinct same-line spans. It checks UTF-8 byte limits, advancing cursors, metadata parity and escaped terminal controls. Full Django diagnostic retrieval has identical ordered edges and an unchanged archive checksum. Both parser environments pass 223 engine tests; the root suite passes 53 tests. Clean wheel and ZIP verification additionally checks both codecs' text output, evidence, actual output budget and absence of a consumer index.
