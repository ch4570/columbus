# Storage cost of preserving distinct Python calls

On two retained Django snapshots with exactly matching indexed path/hash manifests, the complete gzip archive grew from 8,785,093 to 10,726,317 bytes (+22.10%) after adding Python callee spans. SQLite grew from 147,763,200 to 153,387,008 bytes. These are actual regenerated artifacts, not estimates. The corrected snapshot preserves additional same-line calls; reverting that accuracy fix is not an acceptable storage optimization.

Uncompressed reference records grew from 80,677,436 to 95,900,390 bytes, and edge records from 27,969,307 to 31,881,328 bytes. File, scope, import and node bytes were unchanged. Repeated span data in references and edge evidence is therefore the next concrete storage target. The archive remains substantially smaller than SQLite, but the earlier 8.79 MB figure must not describe the corrected graph. The frozen model snapshot has one fewer ignored configuration file and a slightly different archive size; do not compare that snapshot as if identical.

measure.py verifies matching source manifests, regenerates both archives from read-only database connections, and records counts, uncompressed byte attribution and checksums. Temporary archives are deleted afterward. No runtime, compression latency, physical disk I/O or token-saving claim is made. A future compact representation must reconstruct positions losslessly, preserve same-line edge multiplicity, and remain readable through archive search and relationship APIs.

The explicit-UTF-8 test fixture fix at 3c8efc6 passed all six ordinary distribution jobs in run 34163346665; utf8-ci.json records the exact head and conclusions. The later module-qualified lookup at ca66647 is outside that run's scope and remains under its own CI.

## Lossless coordinate-array probe

compact_probe.py replaced the four named callee-span coordinates with a fixed-order array in references and encoded edge evidence, while retaining record order. Every one of 392,163 decoded rows (including embedded evidence strings) reconstructed exactly; 214,126 records changed representation. gzip shrank from 10,726,317 to 10,374,534 bytes, only 3.28%. compact-probe.json retains this result. Temporary artifacts were deleted and the production writer/readers were not changed.

This is insufficient evidence to justify a new archive version and compatibility machinery solely for renaming coordinate fields: most field-name repetition already compresses well. Do not claim it reverses the 22.10% storage increase or adopt the prototype as an accepted portable format. Further reductions should address duplicated structures or representation at a broader level while preserving complete reconstruction, call positions and legacy-reader behavior.
