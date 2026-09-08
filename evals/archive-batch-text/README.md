# Archive batch text replay

Compact file references reduced four retained Java `archive-source` batch responses
from **29,767 to 23,123 UTF-8 bytes (22.32%)**, preserving all 25 declaration targets
and 279 physical source rows. Each comparison renders the exact same retained page.

| Retained trial / event | Targets | Source rows | Before bytes | After bytes | Reduction |
| --- | ---: | ---: | ---: | ---: | ---: |
| columbus-1 / item_13 | 11 | 88 | 11,168 | 7,868 | 29.55% |
| columbus-1 / item_18 | 4 | 15 | 3,931 | 3,069 | 21.93% |
| columbus-1 / item_27 | 3 | 28 | 3,664 | 3,035 | 17.17% |
| columbus-2 / item_10 | 7 | 148 | 11,004 | 9,151 | 16.84% |
| Combined | 25 | 279 | 29,767 | 23,123 | 22.32% |

Run from the repository root; the script uses the standard library and the local
renderer without installing dependencies:

```sh
python3 evals/archive-batch-text/measure.py
python3 evals/archive-batch-text/measure.py --check evals/archive-batch-text/report.json
```

[measure.py](measure.py) reads the original compressed event captures without
modifying them. It selects successful batch command results, reconstructs each
packet, and requires the frozen legacy renderer to reproduce retained stdout byte
for byte. It then decodes the compact file references and verifies every metadata
value, source block range, physical line number, and escaped source row.
[report.json](report.json) retains input capture, selected event line, stdout,
metadata, source row, and renderer SHA-256 hashes alongside the byte counts.
The audit emits aggregate evidence only; it does not print conversation content.

This is a renderer replay using the retained Java property-resolution trials.
Source parity covers the escaped physical rows present in their tool stdout.
Actual model token usage, billing changes, and task quality were not measured.
