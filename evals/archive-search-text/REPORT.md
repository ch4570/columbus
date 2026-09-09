# Consistent archive search output option

The completed urlencode model trace attempted `archive-search --format text`, received an argument error, read help and retried in JSON. Add the same json/text choice already supported by archive-neighbors. JSON remains the default; neither ranking nor archive storage changes.

Text contains labelled JSON metadata and declaration rows. It preserves every packet field, including source hashes, signatures, parse markers and uncertainty. The actual UTF-8 rendering plus final newline controls the byte cap, so a bounded text result may retain a different prefix from JSON. Both formats reject pretty output.

The previously unsupported command now succeeds on the unchanged retained Django archive. Its 2,062-byte text output reconstructs the exact JSON packet: five returned declarations from 38 matches, with truncation retained. This is a CLI regression check, not a replay of the model pair or a token measurement. Text is not claimed to be smaller than JSON; the change removes an observed interface mismatch.

Both parser environments pass 227 engine tests; root tests pass 53. Tests reconstruct metadata and declarations, check exact rank-prefix preservation, byte-limit truncation, invalid formats, escaped controls and gzip/XZ equality. Clean wheel/ZIP verification checks the installed text-search command with both codecs, retained IDs/hashes and the byte budget. The failed model pair and its frozen runtime remain unchanged. Repeated source reads, increased total input and the semantic error from that pair still require separate work.
