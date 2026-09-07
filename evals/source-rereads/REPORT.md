# Source reread diagnosis

The retained urlencode traces show more duplicated bounded source in the graph condition, despite fewer unique source lines. This is evidence for reusing returned numbered context before requesting another view of the same source.

| Verified bounded source | Baseline | Graph |
| --- | ---: | ---: |
| Ranges | 26 | 40 |
| Unique physical lines | 1,182 | 873 |
| Source bytes returned | 44,437 | 40,071 |
| Bytes previously returned in the same condition | 3,823 | 10,428 |
| Unverified recognized ranges | 0 | 0 |

measure.py reads completed command events without executing their commands. It recognizes bounded sed/nl reads and emitted archive call-context ranges, verifies frozen source hashes and matches source content against actual command output. Repeated bytes count occurrences after the first retrieval of a physical line in a file, including original newlines. Numbered output is compared as contiguous sequences, allowing one command to print overlapping line numbers from several different files.

This scope excludes rg output, help, skill/reference text, graph metadata, output-format overhead and all model tokens. It is not a full I/O profile or a projection of attainable token savings. Wider control-flow and import reads may be necessary; duplication alone does not prove every repeated byte was avoidable. Event hashes tie the measurement to the unrepeated, completed pair, whose overall token result remains unsuccessful.

The skill now explicitly notes that text context is already hash-verified and numbered, so it can be reused for citations while missing ranges can be read for wider control flow. The skill validator passes. This is a narrow instruction change based on observed duplicate reads, not evidence that a future agent will follow it or produce a correct answer with fewer tokens. No model trial was replayed.
